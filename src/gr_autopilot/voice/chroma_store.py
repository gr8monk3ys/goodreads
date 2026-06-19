from __future__ import annotations

from pathlib import Path

from gr_autopilot.voice.protocols import Exemplar


class ChromaStore:
    """Persistent Chroma-backed vector store. Requires the `voice` extra.

    Vectors are embedded externally and passed in (not via Chroma's built-in
    embedding function) so bge-small's query-only instruction is honored.
    """

    def __init__(self, path: Path, collection: str = "reviews") -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=str(path))
        self._collection = self._client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )

    def upsert(
        self,
        ids: list[str],
        vectors: list[list[float]],
        documents: list[str],
        metadata: list[dict[str, object]],
    ) -> None:
        self._collection.upsert(
            ids=ids, embeddings=vectors, documents=documents, metadatas=metadata
        )

    def query(
        self, vector: list[float], k: int, where: dict[str, object] | None = None
    ) -> list[Exemplar]:
        res = self._collection.query(query_embeddings=[vector], n_results=k, where=where)
        ids = res["ids"][0]
        docs = res["documents"][0] if res["documents"] else [""] * len(ids)
        dists = res["distances"][0] if res["distances"] else [0.0] * len(ids)
        metas = res["metadatas"][0] if res["metadatas"] else [{}] * len(ids)
        out: list[Exemplar] = []
        for id_, doc, dist, md in zip(ids, docs, dists, metas, strict=True):
            out.append(
                Exemplar(id=id_, text=doc or "", score=1.0 - float(dist), metadata=dict(md or {}))
            )
        return out

    def count(self) -> int:
        return int(self._collection.count())
