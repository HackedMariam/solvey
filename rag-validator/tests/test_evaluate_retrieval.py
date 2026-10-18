from __future__ import annotations

from eval.evaluate_retrieval import _ranked_metrics, _threshold_metrics


def test_ranked_metrics_score_expected_sources_at_reciprocal_rank():
    records = [
        {
            "expected_source": "corpus/a.md",
            "hits": [{"source": "corpus/b.md"}, {"source": "corpus/a.md"}],
        },
        {
            "expected_source": "corpus/c.md",
            "hits": [{"source": "corpus/c.md"}],
        },
        {
            "expected_source": "none",
            "hits": [{"source": "corpus/irrelevant.md"}],
        },
    ]

    result = _ranked_metrics(records)

    assert result == {
        "queries": 2,
        "recall@1": 0.5,
        "recall@3": 1.0,
        "recall@5": 1.0,
        "mrr": 0.75,
    }


def test_threshold_metrics_separates_answerable_and_no_answer_scores():
    records = [
        {"top_score": 0.8, "expected_source": "corpus/a.md"},
        {"top_score": 0.7, "expected_source": "corpus/b.md"},
        {"top_score": 0.4, "expected_source": "none"},
        {"top_score": 0.3, "expected_source": "none"},
    ]

    result = _threshold_metrics(records)

    assert result["balanced_accuracy"] == 1.0
    assert result["true_answerable"] == 2
    assert result["false_accept_no_answer"] == 0
    assert result["correct_abstentions"] == 2
    assert result["false_abstentions"] == 0
