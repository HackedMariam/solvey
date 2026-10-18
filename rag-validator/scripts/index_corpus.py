from __future__ import annotations

import argparse
import os
import time
import uuid
from typing import TYPE_CHECKING

from src.pipeline import ROOT, chunks_for_strategy

if TYPE_CHECKING:
    from openai import OpenAI
    from qdrant_client import QdrantClient

EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_SIZE = 1536
EMBEDDING_BATCH_SIZE = 32
EMBEDDING_BATCH_PAUSE_SECONDS = 1.0


def _batches(chunks: list[dict], batch_size: int = EMBEDDING_BATCH_SIZE):
    for start in range(0, len(chunks), batch_size):
        yield chunks[start:start + batch_size]


def _point_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


def _create_collection(client: QdrantClient, name: str, reset: bool) -> None:
    from qdrant_client import models

    if reset and client.collection_exists(name):
        client.delete_collection(name)
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
        )
    else:
        config = client.get_collection(name).config.params.vectors
        if not isinstance(config, models.VectorParams) or config.size != VECTOR_SIZE:
            raise ValueError(
                f"Collection {name} has incompatible vector configuration; "
                f"expected a single {VECTOR_SIZE}-dimension vector"
            )
    client.create_payload_index(
        collection_name=name,
        field_name="category",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )


def _existing_point_ids(client: QdrantClient, collection: str) -> set[str]:
    existing: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=512,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        existing.update(str(point.id) for point in points)
        if offset is None:
            return existing


def _embed_batch(texts: list[str], client: OpenAI) -> list[list[float]]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        dimensions=VECTOR_SIZE,
        encoding_format="float",
    )
    ordered = sorted(response.data, key=lambda item: item.index)
    vectors = [item.embedding for item in ordered]
    if len(vectors) != len(texts) or any(len(vector) != VECTOR_SIZE for vector in vectors):
        raise ValueError("OpenAI returned an unexpected number of embeddings or vector dimension")
    return vectors


def index_chunks(
    client: QdrantClient,
    collection: str,
    chunks: list[dict],
    embedding_client: OpenAI,
    reset: bool,
) -> None:
    from qdrant_client import models

    _create_collection(client, collection, reset)
    existing_ids = set() if reset else _existing_point_ids(client, collection)
    pending = [chunk for chunk in chunks if _point_id(chunk["id"]) not in existing_ids]
    print(f"{collection}: {len(existing_ids)} existing points; {len(pending)} to embed")
    batches = list(_batches(pending))
    for index, batch in enumerate(batches, start=1):
        vectors = _embed_batch([chunk["text"] for chunk in batch], embedding_client)
        points = [
            models.PointStruct(
                id=_point_id(chunk["id"]),
                vector=vector,
                payload={key: value for key, value in chunk.items() if not key.startswith("_")},
            )
            for chunk, vector in zip(batch, vectors, strict=True)
        ]
        client.upsert(collection_name=collection, points=points, wait=True)
        print(f"{collection}: uploaded batch {index}/{len(batches)} ({len(points)} points)")
        if index < len(batches):
            time.sleep(EMBEDDING_BATCH_PAUSE_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Index both chunking strategies in Qdrant.")
    parser.add_argument("--strategies", nargs="+", choices=["recursive", "blocks"], default=["recursive", "blocks"])
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    import tiktoken

    encoder = tiktoken.get_encoding("cl100k_base")
    planned: dict[str, list[dict]] = {}
    for strategy in args.strategies:
        chunks = chunks_for_strategy(strategy)
        if not chunks:
            raise ValueError(f"No chunks produced for {strategy}")
        planned[strategy] = chunks

    estimates = {}
    for strategy, chunks in planned.items():
        tokens = sum(len(encoder.encode(chunk["text"])) for chunk in chunks)
        estimates[strategy] = (len(chunks), tokens)

    print(f"Embedding model: {EMBEDDING_MODEL}")
    for strategy, (count, tokens) in estimates.items():
        print(f"{strategy}: {count} chunks, {tokens:,} input tokens")
    print(
        f"Batch size: {EMBEDDING_BATCH_SIZE}; pause: "
        f"{EMBEDDING_BATCH_PAUSE_SECONDS:.1f}s between batches"
    )

    from dotenv import load_dotenv
    from openai import OpenAI
    from qdrant_client import QdrantClient

    load_dotenv(ROOT / ".env")
    configured_model = os.getenv("EMBEDDING_MODEL", EMBEDDING_MODEL)
    if configured_model != EMBEDDING_MODEL:
        raise ValueError(f"EMBEDDING_MODEL must be exactly {EMBEDDING_MODEL}; got {configured_model!r}")
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    if not qdrant_url or not qdrant_api_key or not openai_key:
        raise ValueError("Set OPENAI_API_KEY, QDRANT_URL, and QDRANT_API_KEY in .env before indexing")

    qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    embedding_client = OpenAI(api_key=openai_key, max_retries=5, timeout=60)
    for strategy, chunks in planned.items():
        index_chunks(qdrant, f"it_kb_{strategy}", chunks, embedding_client, args.reset)
        print(f"Indexed {len(chunks)} chunks in it_kb_{strategy}")


if __name__ == "__main__":
    main()
