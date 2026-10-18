import json

import pytest

from so_pipeline.apiclient import QuotaExceededError, StackExchangeClient
from so_pipeline.pipeline import (attach_resolution, classify_candidate,
                                  pick_resolution, select_for_subcategory)
from so_pipeline.taxonomy import SearchSpec


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        if self.payload is None:
            raise ValueError("bad json")
        return self.payload


class FakeSession:
    """Scripted session: list of responses (or Exceptions) consumed in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None, stream=False):
        self.calls.append({"url": url, "params": dict(params or {})})
        if not self.responses:
            raise AssertionError("no more scripted responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_client(tmp_path, responses, **kw):
    session = FakeSession(responses)
    client = StackExchangeClient("key", tmp_path / "cache", session=session,
                                 sleep=lambda s: None, pause=0, **kw)
    return client, session


PAGE1 = {"items": [{"question_id": 1}, {"question_id": 2}],
         "has_more": True, "quota_max": 10000, "quota_remaining": 9990}
PAGE2 = {"items": [{"question_id": 3}], "has_more": False,
         "quota_max": 10000, "quota_remaining": 9989}
EMPTY = {"items": [], "has_more": False, "quota_max": 10000, "quota_remaining": 9988}


def test_pagination_follows_has_more(tmp_path):
    client, session = make_client(tmp_path, [FakeResponse(PAGE1), FakeResponse(PAGE2)])
    spec = SearchSpec("q", "vpn failure", "relevance")
    items, pages, has_more = client.search_spec(spec, max_pages=5)
    assert [i["question_id"] for i in items] == [1, 2, 3]
    assert pages == 2
    assert has_more is False
    assert len(session.calls) == 2
    assert session.calls[0]["params"]["page"] == 1
    assert session.calls[1]["params"]["page"] == 2


def test_pagination_stops_at_max_pages(tmp_path):
    client, _ = make_client(tmp_path, [FakeResponse(PAGE1), FakeResponse(PAGE1)])
    spec = SearchSpec("q", "vpn failure", "relevance")
    items, pages, has_more = client.search_spec(spec, max_pages=2)
    assert pages == 2
    assert has_more is True  # more remained but we stopped at max_pages


def test_cache_prevents_second_network_call(tmp_path):
    client, session = make_client(tmp_path, [FakeResponse(PAGE1)])
    spec = SearchSpec("q", "vpn failure", "relevance")
    client.search_spec(spec, max_pages=1)
    assert len(session.calls) == 1
    # fresh client, same cache dir: replay without network
    client2 = StackExchangeClient("key", tmp_path / "cache", session=FakeSession([]),
                                  sleep=lambda s: None, pause=0)
    items, pages, _ = client2.search_spec(spec, max_pages=1)
    assert [i["question_id"] for i in items] == [1, 2]
    assert client2.cache_hits == 1
    assert client2.api_calls == 0


def test_backoff_is_honored(tmp_path):
    slept = []
    session = FakeSession([FakeResponse({**PAGE1, "backoff": 7}),
                           FakeResponse(EMPTY)])
    client = StackExchangeClient("key", tmp_path / "cache", session=session,
                                 sleep=slept.append, pause=0)
    client.search_spec(SearchSpec("q", "x", "relevance"), max_pages=2)
    assert 7 in slept


def test_transient_error_retried(tmp_path):
    import requests
    client, session = make_client(tmp_path, [
        requests.ConnectionError("boom"),
        FakeResponse(PAGE2),
    ])
    items = client.search_page("q", "vpn", "relevance", 1)
    assert items == [{"question_id": 3}]


def test_quota_guard_raises(tmp_path):
    client, _ = make_client(tmp_path, [], min_quota=50)
    client.quota_remaining = 10
    with pytest.raises(QuotaExceededError):
        client.get("/search/advanced", {"q": "x"})


def test_answers_batched_and_sorted(tmp_path):
    ans_page = {
        "items": [
            {"answer_id": 11, "question_id": 1, "score": 1, "is_accepted": False, "body": "low"},
            {"answer_id": 12, "question_id": 1, "score": 9, "is_accepted": True, "body": "acc"},
        ],
        "has_more": False, "quota_max": 10000, "quota_remaining": 9990,
    }
    client, session = make_client(tmp_path, [FakeResponse(ans_page)])
    answers = client.get_answers([1, 2])
    assert set(answers) == {1}
    assert answers[1][0]["score"] >= answers[1][-1]["score"]  # votes desc
    assert "/questions/1;2/answers" in session.calls[0]["url"]


# ---------------- resolution + selection (existing conventions) ---------------- #

def test_pick_resolution_prefers_accepted_then_top_voted():
    acc = {"is_accepted": True, "score": 0}
    top = {"is_accepted": False, "score": 10}
    assert pick_resolution([]) == (None, "none")
    assert pick_resolution([top, acc])[1] == "accepted"
    assert pick_resolution([top])[1] == "top_voted"


def _cand(qid, diff, status, conf=0.7):
    return {"question_id": qid, "difficulty": diff, "resolution_status": status,
            "difficulty_confidence": conf, "score": 0}


def test_selection_prioritizes_none_and_keeps_some_resolved():
    pool = ([_cand(i, "easy", "none") for i in range(10)]
            + [_cand(100 + i, "easy", "accepted") for i in range(10)])
    selected, leftover, mix = select_for_subcategory({}, pool, target=10)
    assert len(selected) == 10
    assert mix["none"] == 6          # 60% none priority
    assert mix["accepted"] == 4      # resolved kept as comparison examples
    assert len(leftover) == 10


def test_selection_respects_baseline_counts():
    pool = [_cand(i, "hard", "none") for i in range(8)]
    selected, leftover, _ = select_for_subcategory({"hard": 15}, pool, target=20)
    assert len(selected) == 5        # only 5 needed to reach 20


def test_attach_resolution_and_classify():
    cand = {"question_id": "5", "title": "How do I reset my password?",
            "description": "I forgot my password.", "tags": "windows"}
    answers_for_q = [{"answer_id": 1, "score": 3, "is_accepted": True,
                      "body": "<p>Use the reset wizard.</p>",
                      "owner": {"display_name": "alice"}}]
    attach_resolution(cand, answers_for_q)
    assert cand["resolution_status"] == "accepted"
    assert cand["has_answer"] is True
    assert "reset wizard" in cand["resolution"]
    classify_candidate(cand)
    assert cand["difficulty"] in ("easy", "medium", "hard")
