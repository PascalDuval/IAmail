from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .indexer import chunk_text


class SQLiteVectorIndexer:
    def __init__(
        self,
        db_path: str | Path = "data/mail_ai.db",
        collection_name: str = "mail_chunks",
        embedding_model: str | None = None,
        ollama_host: str | None = None,
        chunk_size: int = 1200,
        chunk_overlap: int = 120,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.collection_name = collection_name
        self.embedding_model = embedding_model or os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self._client = None
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS vector_chunks (
                    id TEXT PRIMARY KEY,
                    collection_name TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    document TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_vector_chunks_collection ON vector_chunks(collection_name)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_vector_chunks_doc_id ON vector_chunks(doc_id)"
            )

    def _get_client(self):
        if self._client is None:
            try:
                from ollama import Client as OllamaClient
            except ModuleNotFoundError as exc:
                raise RuntimeError("Ollama n'est pas installe: le mode hybride SQLite-vector est indisponible.") from exc
            self._client = OllamaClient(host=self.ollama_host)
        return self._client

    def _embed(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        response = client.embed(model=self.embedding_model, input=texts)
        embeddings = response.get("embeddings", [])
        if not embeddings:
            raise RuntimeError("Ollama n'a retourne aucun embedding.")
        return embeddings

    def reset_collection(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM vector_chunks WHERE collection_name = ?",
                (self.collection_name,),
            )

    def index_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> int:
        metadata = metadata or {}
        chunks = chunk_text(text, chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
        if not chunks:
            return 0

        embeddings = self._embed(chunks)
        now_iso = datetime.now(UTC).isoformat()

        with self._connect() as connection:
            connection.execute(
                "DELETE FROM vector_chunks WHERE collection_name = ? AND doc_id = ?",
                (self.collection_name, doc_id),
            )

            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_id = f"{doc_id}:{idx}"
                chunk_metadata = {
                    **metadata,
                    "doc_id": doc_id,
                    "chunk_index": idx,
                    "chunk_size": len(chunk),
                }
                connection.execute(
                    """
                    INSERT OR REPLACE INTO vector_chunks (
                        id,
                        collection_name,
                        doc_id,
                        chunk_index,
                        document,
                        metadata_json,
                        embedding_json,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        self.collection_name,
                        doc_id,
                        idx,
                        chunk,
                        json.dumps(chunk_metadata, ensure_ascii=True),
                        json.dumps(embedding, ensure_ascii=True),
                        now_iso,
                        now_iso,
                    ),
                )

        return len(chunks)

    def semantic_search(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []

        query_embedding = self._embed([query])[0]

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, document, metadata_json, embedding_json
                FROM vector_chunks
                WHERE collection_name = ?
                """,
                (self.collection_name,),
            ).fetchall()

        if not rows:
            return []

        ranked: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            try:
                embedding = json.loads(str(row["embedding_json"]))
                metadata = json.loads(str(row["metadata_json"]))
            except Exception:
                continue

            similarity = _cosine_similarity(query_embedding, embedding)
            ranked.append(
                (
                    similarity,
                    {
                        "id": str(row["id"]),
                        "document": str(row["document"]),
                        "metadata": metadata,
                        "distance": float(1.0 - similarity),
                    },
                )
            )

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in ranked[: max(1, n_results)]]

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM vector_chunks WHERE collection_name = ?",
                (self.collection_name,),
            ).fetchone()
        return int(row["total"] if row else 0)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        xf = float(x)
        yf = float(y)
        dot += xf * yf
        norm_a += xf * xf
        norm_b += yf * yf

    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))
