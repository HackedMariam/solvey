"""Cached, resumable Stack Exchange API client (respects quota, backoff, pagination)."""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger("so_pipeline.api")

API_BASE = "https://api.stackexchange.com/2.3"
RETRYABLE_STATUS = {502, 503, 504}
MAX_RETRIES = 3


class QuotaExceededError(RuntimeError):
    pass


class StackExchangeClient:
    """Thin wrapper over the Stack Exchange API with a write-through disk cache.

    Every successful response is cached under ``cache_dir`` keyed by a hash of
    the endpoint path + parameters, so re-running the pipeline replays cached
    pages instead of re-hitting the API. Set ``refresh=True`` to bypass.
    """

    def __init__(self, api_key, cache_dir, refresh=False, min_quota=50,
                 session=None, sleep=time.sleep, pause=0.5):
        self.api_key = api_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.refresh = refresh
        self.min_quota = min_quota
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "SolveyPipeline/1.0 (educational research)")
        self.sleep = sleep
        self.pause = pause
        self.quota_remaining = None
        self.quota_max = None
        self.api_calls = 0
        self.cache_hits = 0
        self.failures = []

    # ---------- internals ----------

    def _cache_path(self, path, params):
        key = path + "|" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _load_cache(self, cache_path):
        if self.refresh or not cache_path.exists():
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                entry = json.load(f)
            return entry.get("data")
        except (json.JSONDecodeError, OSError):
            return None

    def _save_cache(self, cache_path, path, params, data):
        entry = {
            "path": path,
            "params": params,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        tmp = cache_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False)
        os.replace(tmp, cache_path)

    def get(self, path, params):
        """GET ``path`` with ``params`` (+ key/site), cache-backed."""
        params = {k: v for k, v in params.items() if v is not None}
        params["key"] = self.api_key
        cache_path = self._cache_path(path, params)
        cached = self._load_cache(cache_path)
        if cached is not None:
            self.cache_hits += 1
            self._track_quota(cached)
            return cached

        if (self.quota_remaining is not None
                and self.quota_remaining < self.min_quota):
            raise QuotaExceededError(
                f"quota_remaining={self.quota_remaining} below min_quota={self.min_quota}")

        url = f"{API_BASE}{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as e:
                wait = 2 ** attempt
                log.warning("request failed (%s), retry %d/%d in %ss", e, attempt, MAX_RETRIES, wait)
                if attempt == MAX_RETRIES:
                    self.failures.append({"path": path, "error": str(e), "params": _public_params(params)})
                    return None
                self.sleep(wait)
                continue

            if resp.status_code in RETRYABLE_STATUS:
                wait = 2 ** attempt
                log.warning("HTTP %s, retry %d/%d in %ss", resp.status_code, attempt, MAX_RETRIES, wait)
                if attempt == MAX_RETRIES:
                    self.failures.append({"path": path, "error": f"HTTP {resp.status_code}",
                                          "params": _public_params(params)})
                    return None
                self.sleep(wait)
                continue

            try:
                data = resp.json()
            except ValueError:
                self.failures.append({"path": path, "error": "non-JSON response",
                                      "params": _public_params(params)})
                return None

            self.api_calls += 1
            self._track_quota(data)

            if "error_id" in data:
                # 502 = throttle; back off and retry
                if data.get("error_id") == 502:
                    wait = data.get("backoff", 2 ** (attempt + 1))
                    log.warning("API throttle (502), sleeping %ss", wait)
                    self.sleep(wait)
                    if attempt == MAX_RETRIES:
                        self.failures.append({"path": path, "error": "throttled",
                                              "params": _public_params(params)})
                        return None
                    continue
                self.failures.append({"path": path, "error": data.get("error_message", "api error"),
                                      "error_id": data.get("error_id"),
                                      "params": _public_params(params)})
                return None

            backoff = data.get("backoff")
            if backoff:
                log.info("API requested backoff: %ss", backoff)
                self.sleep(backoff)

            if (self.quota_remaining is not None
                    and self.quota_remaining <= max(self.min_quota, 10)):
                log.warning("API quota nearly exhausted: %s remaining", self.quota_remaining)

            self._save_cache(cache_path, path, params, data)
            return data

        return None

    def _track_quota(self, data):
        if not isinstance(data, dict):
            return
        if data.get("quota_remaining") is not None:
            self.quota_remaining = data["quota_remaining"]
        if data.get("quota_max") is not None:
            self.quota_max = data["quota_max"]

    # ---------- endpoints ----------

    def _search_params(self, spec_kind, value, sort, page, pagesize=50):
        if spec_kind == "q":
            path = "/search/advanced"
            params = {"q": value, "sort": sort, "order": "desc",
                      "page": page, "pagesize": pagesize, "site": "stackoverflow",
                      "filter": "withbody"}
        elif spec_kind == "tagged":
            path = "/search"
            params = {"tagged": value, "sort": sort if sort != "relevance" else "activity",
                      "order": "desc", "page": page, "pagesize": pagesize,
                      "site": "stackoverflow", "filter": "withbody"}
        else:
            raise ValueError(f"unknown spec kind: {spec_kind}")
        return path, params

    def search_page(self, spec_kind, value, sort, page, pagesize=50):
        """One page of question search results. Returns list of items or None on failure."""
        path, params = self._search_params(spec_kind, value, sort, page, pagesize)
        data = self.get(path, params)
        if data is None:
            return None
        return data.get("items", [])

    def search_spec(self, spec, max_pages=2):
        """All pages of one SearchSpec, honoring has_more.

        Returns (items, pages_fetched, has_more_at_stop).
        """
        items = []
        pages_fetched = 0
        has_more = False
        for page in range(1, max_pages + 1):
            path, params = self._search_params(spec.kind, spec.value, spec.sort, page)
            data = self.get(path, params)
            if data is None:
                break
            pages_fetched += 1
            batch = data.get("items", [])
            if not batch:
                has_more = False
                break
            items.extend(batch)
            has_more = bool(data.get("has_more", False))
            if not has_more or page == max_pages:
                break
            self.sleep(self.pause)
        return items, pages_fetched, has_more

    def get_answers(self, question_ids, pagesize=100):
        """Fetch answers for up to N question ids (batched 100/page, paginated).

        Returns dict question_id -> list[answer dicts] (votes desc). Failed
        batches are recorded in self.failures and skipped.
        """
        answers = {}
        ids = sorted(str(q) for q in question_ids)
        for i in range(0, len(ids), 100):
            chunk = ids[i:i + 100]
            id_path = ";".join(chunk)
            page = 1
            while True:
                data = self.get(f"/questions/{id_path}/answers", {
                    "order": "desc", "sort": "votes", "site": "stackoverflow",
                    "filter": "withbody", "pagesize": pagesize, "page": page,
                })
                if data is None:
                    break
                for ans in data.get("items", []):
                    answers.setdefault(ans.get("question_id"), []).append(ans)
                if not data.get("has_more", False):
                    break
                page += 1
                self.sleep(self.pause)
            self.sleep(self.pause)
        # keep votes-desc order per question
        for qid, lst in answers.items():
            lst.sort(key=lambda a: a.get("score", 0), reverse=True)
        return answers

    def validate_tags(self, tags, batch=20):
        """Check which SO tags exist via /tags/{tags}/info. Returns (valid, invalid)."""
        valid, invalid = [], []
        tags = sorted(set(tags))
        for i in range(0, len(tags), batch):
            chunk = tags[i:i + batch]
            data = self.get(f"/tags/{';'.join(chunk)}/info", {"site": "stackoverflow"})
            if data is None:
                # cannot verify: keep tags optimistically, log
                valid.extend(chunk)
                continue
            found = {item["name"] for item in data.get("items", [])}
            for t in chunk:
                (valid if t in found else invalid).append(t)
            self.sleep(self.pause)
        return valid, invalid


def _public_params(params):
    return {k: v for k, v in params.items() if k != "key"}
