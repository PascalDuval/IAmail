from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import chromadb
from ollama import Client


def chunk_text(text: str, chunk_size: int = 1200, chunk_overlap: int = 120) -> list[str]:
	cleaned = " ".join(text.split())
	if not cleaned:
		return []

	if chunk_overlap >= chunk_size:
		raise ValueError("chunk_overlap doit etre strictement inferieur a chunk_size")

	chunks: list[str] = []
	start = 0
	step = chunk_size - chunk_overlap

	while start < len(cleaned):
		chunk = cleaned[start : start + chunk_size].strip()
		if chunk:
			chunks.append(chunk)
		start += step

	return chunks


class OllamaEmbeddingFunction:
	def __init__(self, model: str, host: str) -> None:
		self.model = model
		self.client = Client(host=host)

	def __call__(self, input: list[str]) -> list[list[float]]:
		response = self.client.embed(model=self.model, input=input)
		embeddings = response.get("embeddings", [])
		if not embeddings:
			raise RuntimeError("Ollama n'a retourne aucun embedding.")
		return embeddings

	def name(self) -> str:
		return "ollama"

	def embed_documents(self, input: list[str]) -> list[list[float]]:
		return self.__call__(input)

	def embed_query(self, input: list[str]) -> list[list[float]]:
		return self.__call__(input)


class SemanticIndexer:
	def __init__(
		self,
		persist_directory: str | Path = "data/chroma_db",
		collection_name: str = "mail_chunks",
		embedding_model: str | None = None,
		ollama_host: str | None = None,
		chunk_size: int = 1200,
		chunk_overlap: int = 120,
	) -> None:
		self.persist_directory = Path(persist_directory)
		self.persist_directory.mkdir(parents=True, exist_ok=True)

		self.collection_name = collection_name
		self.embedding_model = embedding_model or os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
		self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
		self.chunk_size = chunk_size
		self.chunk_overlap = chunk_overlap

		self.client = chromadb.PersistentClient(path=str(self.persist_directory))
		self.embedding_function = OllamaEmbeddingFunction(
			model=self.embedding_model,
			host=self.ollama_host,
		)
		self.collection = self.client.get_or_create_collection(
			name=self.collection_name,
			metadata={
				"hnsw:space": "cosine",
				"description": "Mail IA semantic chunks",
			},
			embedding_function=self.embedding_function,
		)

	def reset_collection(self) -> None:
		try:
			self.client.delete_collection(self.collection_name)
		except Exception:
			pass

		self.collection = self.client.get_or_create_collection(
			name=self.collection_name,
			metadata={
				"hnsw:space": "cosine",
				"description": "Mail IA semantic chunks",
			},
			embedding_function=self.embedding_function,
		)

	def index_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> int:
		metadata = metadata or {}
		chunks = chunk_text(text, chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
		if not chunks:
			return 0

		ids = [f"{doc_id}:{idx}" for idx, _ in enumerate(chunks)]
		metadatas = [
			{
				**metadata,
				"doc_id": doc_id,
				"chunk_index": idx,
				"chunk_size": len(chunk),
			}
			for idx, chunk in enumerate(chunks)
		]

		self.collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
		return len(chunks)

	def semantic_search(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
		results = self.collection.query(
			query_texts=[query],
			n_results=n_results,
		)

		ids = results.get("ids", [[]])[0]
		documents = results.get("documents", [[]])[0]
		metadatas = results.get("metadatas", [[]])[0]
		distances = results.get("distances", [[]])[0]

		output: list[dict[str, Any]] = []
		for idx, chunk_id in enumerate(ids):
			output.append(
				{
					"id": chunk_id,
					"document": documents[idx] if idx < len(documents) else "",
					"metadata": metadatas[idx] if idx < len(metadatas) else {},
					"distance": distances[idx] if idx < len(distances) else None,
				}
			)
		return output

	def count(self) -> int:
		return int(self.collection.count())
