from __future__ import annotations

from typing import cast


class SentenceTransformerEmbedder:
    """Local bge-small embedder (sentence-transformers). Requires the `voice` extra.

    The bge query instruction is applied to queries ONLY, never to documents.
    """

    _QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self._dimension = int(self._model.get_sentence_embedding_dimension())

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return cast("list[list[float]]", vectors.tolist())

    def embed_query(self, text: str) -> list[float]:
        vector = self._model.encode(
            self._QUERY_INSTRUCTION + text, normalize_embeddings=True
        )
        return cast("list[float]", vector.tolist())
