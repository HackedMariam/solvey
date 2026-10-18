from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[1]
QUERY_PATH = ROOT / "eval" / "test_queries_draft.csv"
OUTPUT_PATH = ROOT / "eval" / "results" / "retrieval_results.json"
COLLECTIONS = {
    "A": "it_kb_recursive",
    "B": "it_kb_blocks",
}
EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_SIZE = 1536
TOP_K = 5


def _normalize_source(source: Any) -> str | None:
    if not isinstance(source, str):
        return None
    return source.replace("\\", "/").lstrip("./")


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _ranked_metrics(records: list[dict[str, Any]]) -> dict[str, float | int | None]:
    answerable = [record for record in records if record["expected_source"] != "none"]
    if not answerable:
        return {"queries": 0, "recall@1": None, "recall@3": None, "recall@5": None, "mrr": None}

    reciprocal_ranks: list[float] = []
    recalls = {1: 0, 3: 0, 5: 0}
    for record in answerable:
        expected = _normalize_source(record["expected_source"])
        ranked_sources = [_normalize_source(hit.get("source")) for hit in record["hits"]]
        rank = next((index for index, source in enumerate(ranked_sources, start=1) if source == expected), None)
        if rank is not None:
            reciprocal_ranks.append(1 / rank)
            for cutoff in recalls:
                if rank <= cutoff:
                    recalls[cutoff] += 1
        else:
            reciprocal_ranks.append(0.0)

    count = len(answerable)
    return {
        "queries": count,
        "recall@1": recalls[1] / count,
        "recall@3": recalls[3] / count,
        "recall@5": recalls[5] / count,
        "mrr": sum(reciprocal_ranks) / count,
    }


def _threshold_metrics(records: list[dict[str, Any]]) -> dict[str, float | int]:
    labelled = [
        (float(record["top_score"]), record["expected_source"] != "none")
        for record in records
        if record["top_score"] is not None
    ]
    if not labelled:
        raise ValueError("No top scores available to evaluate abstention threshold")

    scores = sorted({score for score, _ in labelled})
    candidates = [scores[0] - 1e-9]
    candidates.extend((left + right) / 2 for left, right in zip(scores, scores[1:]))
    candidates.append(scores[-1] + 1e-9)

    best: tuple[float, float, int, int, int, int] | None = None
    for threshold in candidates:
        tp = fp = tn = fn = 0
        for score, answerable in labelled:
            predicted_answerable = score >= threshold
            if predicted_answerable and answerable:
                tp += 1
            elif predicted_answerable:
                fp += 1
            elif answerable:
                fn += 1
            else:
                tn += 1
        sensitivity = tp / (tp + fn) if tp + fn else 0.0
        specificity = tn / (tn + fp) if tn + fp else 0.0
        balanced_accuracy = (sensitivity + specificity) / 2
        candidate = (balanced_accuracy, threshold, tp, fp, tn, fn)
        if best is None or candidate[0] > best[0] or (
            candidate[0] == best[0] and candidate[1] > best[1]
        ):
            best = candidate

    assert best is not None
    balanced_accuracy, threshold, tp, fp, tn, fn = best
    return {
        "threshold": threshold,
        "balanced_accuracy": balanced_accuracy,
        "true_answerable": tp,
        "false_accept_no_answer": fp,
        "correct_abstentions": tn,
        "false_abstentions": fn,
    }


def _score_distribution(records: list[dict[str, Any]]) -> dict[str, dict[str, float | int | None]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for record in records:
        if record["top_score"] is not None:
            label = "no_answer" if record["expected_source"] == "none" else "answerable"
            groups[label].append(float(record["top_score"]))
    return {
        label: {
            "count": len(scores),
            "min": min(scores) if scores else None,
            "mean": _mean(scores),
            "median": sorted(scores)[len(scores) // 2] if scores else None,
            "max": max(scores) if scores else None,
        }
        for label, scores in groups.items()
    }


def main() -> None:
    load_dotenv(ROOT / ".env")
    openai_key = os.getenv("OPENAI_API_KEY")
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_key = os.getenv("QDRANT_API_KEY")
    if not openai_key or not qdrant_url or not qdrant_key:
        raise ValueError("Set OPENAI_API_KEY, QDRANT_URL, and QDRANT_API_KEY in .env")

    with QUERY_PATH.open(encoding="utf-8-sig", newline="") as stream:
        queries = list(csv.DictReader(stream))
    if len(queries) != 30:
        raise ValueError(f"Expected 30 evaluation queries, found {len(queries)}")
    allowed_types = {"paraphrase", "table", "exact_title", "no_answer"}
    for row in queries:
        if row.get("type") not in allowed_types:
            raise ValueError(f"Unexpected query type for {row.get('query_id')}: {row.get('type')}")
        if not row.get("query") or not row.get("category"):
            raise ValueError(f"Missing query text or category for {row.get('query_id')}")

    embedding_client = OpenAI(api_key=openai_key, max_retries=5, timeout=60)
    qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_key)
    for label, collection in COLLECTIONS.items():
        info = qdrant.get_collection(collection)
        vector_config = info.config.params.vectors
        if getattr(vector_config, "size", None) != VECTOR_SIZE:
            raise ValueError(f"{collection} does not use {VECTOR_SIZE}-dimension vectors")

    output: dict[str, Any] = {
        "embedding_model": EMBEDDING_MODEL,
        "top_k": TOP_K,
        "query_count": len(queries),
        "collections": {},
    }
    results: dict[tuple[str, str], list[dict[str, Any]]] = {
        (label, filter_mode): []
        for label in COLLECTIONS
        for filter_mode in ("unfiltered", "filtered")
    }

    for number, row in enumerate(queries, start=1):
        vector = embedding_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[row["query"]],
            dimensions=VECTOR_SIZE,
            encoding_format="float",
        ).data[0].embedding
        if len(vector) != VECTOR_SIZE:
            raise ValueError(f"Unexpected query embedding dimension for {row['query_id']}")

        expected = row["expected_source"] or "none"
        for label, collection in COLLECTIONS.items():
            for filter_mode in ("unfiltered", "filtered"):
                query_filter = None
                if filter_mode == "filtered":
                    from qdrant_client import models

                    query_filter = models.Filter(
                        must=[
                            models.FieldCondition(
                                key="category",
                                match=models.MatchValue(value=row["category"]),
                            )
                        ]
                    )
                points = qdrant.query_points(
                    collection_name=collection,
                    query=vector,
                    query_filter=query_filter,
                    limit=TOP_K,
                    with_payload=True,
                ).points
                hits = [
                    {
                        "source": (point.payload or {}).get("source"),
                        "score": float(point.score),
                        "title": (point.payload or {}).get("title"),
                    }
                    for point in points
                ]
                results[(label, filter_mode)].append({
                    "query_id": row["query_id"],
                    "type": row["type"],
                    "category": row["category"],
                    "expected_source": expected,
                    "top_score": hits[0]["score"] if hits else None,
                    "top_source": hits[0]["source"] if hits else None,
                    "hits": hits,
                })

        print(f"[{number:02d}/{len(queries)}] {row['query_id']} ({row['type']}) complete", flush=True)

    for label in COLLECTIONS:
        output["collections"][label] = {}
        for filter_mode in ("unfiltered", "filtered"):
            records = results[(label, filter_mode)]
            threshold = _threshold_metrics(records)
            by_type = {}
            for query_type in ("paraphrase", "table", "exact_title", "no_answer"):
                type_records = [record for record in records if record["type"] == query_type]
                metric = _ranked_metrics(type_records)
                metric["query_count"] = len(type_records)
                if query_type == "no_answer":
                    scores = [float(record["top_score"]) for record in type_records if record["top_score"] is not None]
                    metric["top_score_mean"] = _mean(scores)
                    metric["top_score_max"] = max(scores) if scores else None
                    metric["above_threshold"] = sum(score >= threshold["threshold"] for score in scores)
                by_type[query_type] = metric
            output["collections"][label][filter_mode] = {
                "overall": _ranked_metrics(records),
                "by_type": by_type,
                "score_distribution": _score_distribution(records),
                "abstention_threshold": threshold,
                "queries": records,
            }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for label in COLLECTIONS:
        print(f"\n{label} ({COLLECTIONS[label]})")
        for filter_mode in ("unfiltered", "filtered"):
            report = output["collections"][label][filter_mode]
            metrics = report["overall"]
            print(
                f"  {filter_mode}: Recall@1={metrics['recall@1']:.3f}, "
                f"Recall@3={metrics['recall@3']:.3f}, Recall@5={metrics['recall@5']:.3f}, "
                f"MRR={metrics['mrr']:.3f}; threshold={report['abstention_threshold']['threshold']:.4f}"
            )
            for query_type, type_metrics in report["by_type"].items():
                if query_type == "no_answer":
                    print(
                        f"    {query_type}: n={type_metrics['query_count']}, "
                        f"top score mean/max={type_metrics['top_score_mean']:.3f}/"
                        f"{type_metrics['top_score_max']:.3f}, above threshold="
                        f"{type_metrics['above_threshold']}"
                    )
                else:
                    print(
                        f"    {query_type}: n={type_metrics['query_count']}, "
                        f"R@1/3/5={type_metrics['recall@1']:.3f}/"
                        f"{type_metrics['recall@3']:.3f}/{type_metrics['recall@5']:.3f}, "
                        f"MRR={type_metrics['mrr']:.3f}"
                    )
            print(f"    score distribution: {report['score_distribution']}")
    print(f"\nDetailed query results: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
