from __future__ import annotations

import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .indexer import SemanticIndexer
from .llm import OllamaLLM
from .sqlite_vector_indexer import SQLiteVectorIndexer
from .structured_store import StructuredStore


@dataclass
class QueryResult:
	question: str
	answer: str
	structured_hits: list[dict[str, Any]]
	semantic_hits: list[dict[str, Any]]
	context: str


class QueryEngine:
	def __init__(
		self,
		store: StructuredStore,
		indexer: Any | None,
		llm: OllamaLLM | None,
	) -> None:
		self.store = store
		self.indexer = indexer
		self.llm = llm

	@classmethod
	def from_env(
		cls,
		db_path: str | Path | None = None,
		chroma_path: str | Path | None = None,
		collection_name: str = "mail_chunks",
		enable_semantic: bool = False,
		enable_llm: bool = False,
		semantic_backend: str = "sqlite-vector",
	) -> "QueryEngine":
		load_dotenv()

		store_path = Path(db_path or os.getenv("MAIL_AI_DB_PATH", "data/mail_ai.db"))
		chroma_dir = Path(chroma_path or os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db"))

		store = StructuredStore(db_path=store_path)
		store.init_schema()
		selected_backend = (semantic_backend or os.getenv("SEMANTIC_BACKEND", "sqlite-vector")).strip().lower()
		indexer: Any | None = None
		if enable_semantic:
			if selected_backend == "chroma":
				indexer = SemanticIndexer(
					persist_directory=chroma_dir,
					collection_name=collection_name,
					chunk_size=1200,
					chunk_overlap=120,
				)
			elif selected_backend == "sqlite-vector":
				indexer = SQLiteVectorIndexer(
					db_path=store_path,
					collection_name=collection_name,
					chunk_size=1200,
					chunk_overlap=120,
				)
			else:
				raise ValueError(
					f"Backend semantique inconnu: {selected_backend}. Utiliser 'sqlite-vector' ou 'chroma'."
				)
		llm: OllamaLLM | None = OllamaLLM.from_env() if enable_llm else None
		return cls(store=store, indexer=indexer, llm=llm)

	def build_context(self, question: str, structured_limit: int = 5, semantic_limit: int = 5) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
		structured_hits = self.store.search_mails(question, limit=structured_limit)
		semantic_hits = self.indexer.semantic_search(question, n_results=semantic_limit) if self.indexer is not None else []

		context_parts = [
			self._format_structured_hits(structured_hits),
			self._format_semantic_hits(semantic_hits),
		]
		context = "\n\n".join(part for part in context_parts if part.strip())
		return structured_hits, semantic_hits, context

	def ask(self, question: str) -> QueryResult:
		structured_hits, semantic_hits, context = self.build_context(question)
		if self.llm is None:
			answer = self._build_safe_answer(question=question, structured_hits=structured_hits)
			return QueryResult(
				question=question,
				answer=answer,
				structured_hits=structured_hits,
				semantic_hits=semantic_hits,
				context=context,
			)

		if not structured_hits and not semantic_hits:
			answer = (
				"Mode safe actif: aucun mail suffisamment pertinent n'a été trouvé dans SQLite pour cette requete. "
				"Essayez une recherche plus précise, par exemple avec un expediteur, un sujet ou un mot distinctif."
			)
			return QueryResult(
				question=question,
				answer=answer,
				structured_hits=[],
				semantic_hits=[],
				context=context,
			)
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

		lines = ["Resultats semantiques (backend hybride):"]
		for hit in semantic_hits:
			snippet = str(hit.get("document", "")).replace("\n", " ").strip()
			lines.append(
				f"- {hit.get('id', '')} | distance={hit.get('distance', '')} | {snippet[:220]}"
			)
		return "\n".join(lines)

	def _build_safe_answer(self, question: str, structured_hits: list[dict[str, Any]]) -> str:
		if self._looks_like_job_summary_question(question):
			job_summary = self._build_job_summary_answer(question=question)
			if job_summary:
				return job_summary

		if not structured_hits:
			return (
				"Mode safe actif: je n'utilise pas Chroma/Ollama pour cette requete. "
				"Aucun mail correspondant n'a ete trouve dans SQLite."
			)

		lines = [
			"Mode safe actif: reponse basee uniquement sur SQLite.",
			f"Question: {question}",
			"Derniers resultats pertinents:",
		]
		for hit in structured_hits[:5]:
			lines.append(
				f"- [{hit.get('sent_at', '')}] {hit.get('sender', '')} | {hit.get('subject', '')} | corps={hit.get('body_size', 0)} caracteres"
			)
		return "\n".join(lines)

	def _build_job_summary_answer(self, question: str) -> str:
		days = self._extract_day_window(question)
		reference_time = datetime.now(UTC)
		window_start = reference_time - timedelta(days=days)
		all_mails = self.store.get_all_mails()
		job_mails: list[dict[str, Any]] = []

		for mail in all_mails:
			sent_at_raw = str(mail.get("sent_at", ""))
			try:
				sent_at = datetime.fromisoformat(sent_at_raw)
			except ValueError:
				continue

			if sent_at.tzinfo is None:
				sent_at = sent_at.replace(tzinfo=UTC)

			if sent_at < window_start:
				continue

			if self._is_job_related_mail(mail):
				job_mails.append(mail)

		if not job_mails:
			return ""

		job_mails.sort(key=lambda item: str(item.get("sent_at", "")), reverse=True)
		sender_counts = Counter(self._sender_domain_or_name(item.get("sender", "")) for item in job_mails)
		theme_counts = Counter(self._extract_job_theme(str(item.get("subject", ""))) for item in job_mails)

		start_label = window_start.date().isoformat()
		end_label = reference_time.date().isoformat()
		lines = [
			"Mode safe actif: reponse basee uniquement sur SQLite.",
			f"Synthese offres d'emploi ({days} jours, du {start_label} au {end_label}): {len(job_mails)} alertes pertinentes.",
		]

		top_senders = [f"{name} ({count})" for name, count in sender_counts.most_common(3)]
		if top_senders:
			lines.append(f"Sources principales: {', '.join(top_senders)}")

		top_themes = [f"{name} ({count})" for name, count in theme_counts.most_common(4) if name]
		if top_themes:
			lines.append(f"Postes/themes dominants: {', '.join(top_themes)}")

		lines.append("Dernieres alertes (max 5):")
		for hit in job_mails[:5]:
			lines.append(
				f"- [{hit.get('sent_at', '')}] {hit.get('sender', '')} | {hit.get('subject', '')} | corps={hit.get('body_size', 0)} caracteres"
			)

		return "\n".join(lines)

	def _looks_like_job_summary_question(self, question: str) -> bool:
		normalized = _normalize_for_rules(question)
		job_keywords = ("offre", "emploi", "job", "recrut", "poste", "candidature")
		summary_keywords = ("resume", "synthese", "dernier", "derniere", "jours", "semaine")
		return any(keyword in normalized for keyword in job_keywords) and any(
			keyword in normalized for keyword in summary_keywords
		)

	def _extract_day_window(self, question: str, default_days: int = 15) -> int:
		normalized = _normalize_for_rules(question)
		match = re.search(r"(\d{1,3})\s*jour", normalized)
		if match:
			return max(1, int(match.group(1)))

		words_to_days = {
			"quinze": 15,
			"sept": 7,
			"huit": 8,
			"dix": 10,
			"trente": 30,
		}
		for word, day_count in words_to_days.items():
			if f"{word} jour" in normalized or f"{word} derniers" in normalized:
				return day_count

		if "2 semaines" in normalized or "deux semaines" in normalized or "quinzaine" in normalized:
			return 15

		if "semaine" in normalized:
			return 7

		if "mois" in normalized:
			return 30

		return default_days

	def _is_job_related_mail(self, mail: dict[str, Any]) -> bool:
		subject = _normalize_for_rules(str(mail.get("subject", "")))
		sender = _normalize_for_rules(str(mail.get("sender", "")))
		body = _normalize_for_rules(str(mail.get("body_text", "")))
		combined = f"{subject} {sender} {body}"
		keywords = (
			"offre",
			"offres",
			"emploi",
			"emplois",
			"job",
			"jobs",
			"recrut",
			"candidature",
			"data scientist",
			"data analyst",
			"france travail",
			"cadremploi",
			"indeed",
		)
		return any(keyword in combined for keyword in keywords)

	def _sender_domain_or_name(self, sender: Any) -> str:
		sender_text = str(sender or "").strip()
		if "@" in sender_text:
			domain = sender_text.split("@", 1)[1].strip().strip(">")
			if domain:
				return domain.lower()
		return sender_text or "inconnu"

	def _extract_job_theme(self, subject: str) -> str:
		normalized = _normalize_for_rules(subject)
		for pattern in (
			r"(data scientist[^|\-]*)",
			r"(data analyst[^|\-]*)",
			r"(machine learning[^|\-]*)",
			r"(ingenieur[^|\-]*data[^|\-]*)",
		):
			match = re.search(pattern, normalized)
			if match:
				return match.group(1).strip()
		return normalized[:60].strip() or "autres"


def _normalize_for_rules(value: str) -> str:
	normalized = unicodedata.normalize("NFKD", value)
	without_accents = "".join(character for character in normalized if not unicodedata.combining(character))
	return " ".join(without_accents.lower().split())
