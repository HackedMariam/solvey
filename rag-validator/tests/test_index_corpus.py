from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.index_corpus import EMBEDDING_MODEL, VECTOR_SIZE, _embed_batch


class FakeEmbeddingClient:
    def __init__(self, data: list[SimpleNamespace]):
        self.data = data
        self.request: dict = {}

    class Embeddings:
        def __init__(self, owner: FakeEmbeddingClient):
            self.owner = owner

        def create(self, **kwargs):
            self.owner.request = kwargs
            return SimpleNamespace(data=self.owner.data)

    @property
    def embeddings(self):
        return self.Embeddings(self)


def test_embed_batch_uses_configured_model_dimension_and_request_order():
    first = [0.1] * VECTOR_SIZE
    second = [0.2] * VECTOR_SIZE
    client = FakeEmbeddingClient([
        SimpleNamespace(index=1, embedding=second),
        SimpleNamespace(index=0, embedding=first),
    ])

    result = _embed_batch(["first", "second"], client)

    assert result == [first, second]
    assert client.request == {
        "model": EMBEDDING_MODEL,
        "input": ["first", "second"],
        "dimensions": VECTOR_SIZE,
        "encoding_format": "float",
    }


def test_embed_batch_rejects_unexpected_vector_dimension():
    client = FakeEmbeddingClient([
        SimpleNamespace(index=0, embedding=[0.0] * (VECTOR_SIZE - 1)),
    ])

    with pytest.raises(ValueError, match="unexpected number of embeddings or vector dimension"):
        _embed_batch(["only"], client)
