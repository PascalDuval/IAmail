from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .indexer import SemanticIndexer
from .llm import OllamaLLM
from .structured_store import StructuredStore


@dataclass
class QueryResult:
	question: str
	answer: str
	structured_hits: list[dict[str, Any]]
	semantic_hits: list[dict[str, Any]]
	context: str


class QueryEngine:
	def __init__(self, store: StructuredStore, indexer: SemanticIndexer, llm: OllamaLLM) -> None:
		self.store = store
		self.indexer = indexer
		self.llm = llm

	def build_context(self, question: str, structured_limit: int = 5, semantic_limit: int = 5) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
		structured_hits = self.store.search_mails(question, limit=structured_limit)
		semantic_hits = self.indexer.semantic_search(question, n_results=semantic_limit)

		context_parts = [
			self._format_structured_hits(structured_hits),
			self._format_semantic_hits(semantic_hits),
		]
		context = "\n\n".join(part for part in context_parts if part.strip())
		return structured_hits, semantic_hits, context

	def ask(self, question: str) -> QueryResult:
		structured_hits, semantic_hits, context = self.build_context(question)
		answer = self.llm.generate_answer(question=question, context=context)
		return QueryResult(
			question=question,
			answer=answer,
			structured_hits=structured_hits,
			semantic_hits=semantic_hits,
			context=context,
		)

	def _format_structured_hits(self, structured_hits: list[dict[str, Any]]) -> str:
		if not structured_hits:
			return "Aucun resultat structure n'a ete trouve."

		lines = ["Resultats structure (SQLite):"]
		for hit in structured_hits:
			lines.append(
				f"- [{hit.get('sent_at', '')}] {hit.get('sender', '')} | {hit.get('subject', '')} | corps={hit.get('body_size', 0)} caracteres"
			)
		return "\n".join(lines)

	def _format_semantic_hits(self, semantic_hits: list[dict[str, Any]]) -> str:
		if not semantic_hits:
			return "Aucun resultat semantique n'a ete trouve."

		lines = ["Resultats semantiques (Chroma):"]
		for hit in semantic_hits:
			snippet = str(hit.get("document", "")).replace("\n", " ").strip()
			lines.append(
				f"- {hit.get('id', '')} | distance={hit.get('distance', '')} | {snippet[:220]}"
			)
		return "\n".join(lines)
