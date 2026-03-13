from __future__ import annotations

from typing import Any


class FakeVectorCollection:
    """Small in-memory vector-store double for unit/integration tests."""

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    def upsert(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        del embeddings
        for idx, row_id in enumerate(ids):
            row = {
                "id": row_id,
                "document": documents[idx],
                "metadata": metadatas[idx] or {},
            }
            for existing_idx, existing in enumerate(self._rows):
                if existing["id"] == row_id:
                    self._rows[existing_idx] = row
                    break
            else:
                self._rows.append(row)

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        include: list[str] | None = None,
    ) -> dict[str, list[list[Any]]]:
        del query_embeddings
        include = include or ["documents", "metadatas", "distances"]
        rows = self._rows[:n_results]
        result: dict[str, list[list[Any]]] = {"ids": [[row["id"] for row in rows]]}
        if "documents" in include:
            result["documents"] = [[row["document"] for row in rows]]
        if "metadatas" in include:
            result["metadatas"] = [[row["metadata"] for row in rows]]
        if "distances" in include:
            result["distances"] = [[0.0 for _ in rows]]
        return result

    def count(self) -> int:
        return len(self._rows)


class FakeVectorStoreRegistry:
    def __init__(self) -> None:
        self._collections: dict[str, FakeVectorCollection] = {}

    def get(self, name: str = "default") -> FakeVectorCollection:
        if name not in self._collections:
            self._collections[name] = FakeVectorCollection()
        return self._collections[name]
