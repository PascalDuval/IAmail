from __future__ import annotations

import sqlite3
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class MailRecord:
	uid: int
	folder: str
	subject: str
	sender: str
	recipients: str
	date: str
	body_text: str
	body_size: int
	attachment_count: int
	message_id: str | None = None


@dataclass
class AttachmentRecord:
	filename: str
	content_type: str
	size_bytes: int
	extracted_text: str = ""


@dataclass
class EntityRecord:
	entity_type: str
	entity_value: str
	confidence: float | None = None
	source: str = "llm"


class StructuredStore:
	def __init__(self, db_path: str | Path = "data/mail_ai.db") -> None:
		self.db_path = Path(db_path)
		self.db_path.parent.mkdir(parents=True, exist_ok=True)

	def _connect(self) -> sqlite3.Connection:
		connection = sqlite3.connect(self.db_path)
		connection.row_factory = sqlite3.Row
		connection.execute("PRAGMA foreign_keys = ON;")
		return connection

	def init_schema(self) -> None:
		with self._connect() as connection:
			connection.executescript(
				"""
				CREATE TABLE IF NOT EXISTS mails (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					uid INTEGER NOT NULL,
					message_id TEXT,
					folder TEXT NOT NULL,
					subject TEXT NOT NULL,
					sender TEXT NOT NULL,
					recipients TEXT NOT NULL,
					sent_at TEXT NOT NULL,
					body_text TEXT NOT NULL,
					body_size INTEGER NOT NULL,
					attachment_count INTEGER NOT NULL,
					created_at TEXT NOT NULL,
					updated_at TEXT NOT NULL,
					UNIQUE(uid, folder)
				);

				CREATE TABLE IF NOT EXISTS attachments (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					mail_id INTEGER NOT NULL,
					filename TEXT NOT NULL,
					content_type TEXT NOT NULL,
					size_bytes INTEGER NOT NULL,
					extracted_text TEXT NOT NULL,
					created_at TEXT NOT NULL,
					FOREIGN KEY(mail_id) REFERENCES mails(id) ON DELETE CASCADE
				);

				CREATE TABLE IF NOT EXISTS entities (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					mail_id INTEGER NOT NULL,
					entity_type TEXT NOT NULL,
					entity_value TEXT NOT NULL,
					confidence REAL,
					source TEXT NOT NULL,
					created_at TEXT NOT NULL,
					FOREIGN KEY(mail_id) REFERENCES mails(id) ON DELETE CASCADE
				);

				CREATE INDEX IF NOT EXISTS idx_mails_sent_at ON mails(sent_at);
				CREATE INDEX IF NOT EXISTS idx_attachments_mail_id ON attachments(mail_id);
				CREATE INDEX IF NOT EXISTS idx_entities_mail_id ON entities(mail_id);
				"""
			)

			# Index full-text safe/local sans dependance Chroma.
			try:
				connection.executescript(
					"""
					CREATE VIRTUAL TABLE IF NOT EXISTS mails_fts USING fts5(
						subject,
						sender,
						recipients,
						body_text,
						content='mails',
						content_rowid='id',
						tokenize='unicode61 remove_diacritics 2'
					);

					CREATE TRIGGER IF NOT EXISTS mails_ai AFTER INSERT ON mails BEGIN
						INSERT INTO mails_fts(rowid, subject, sender, recipients, body_text)
						VALUES (new.id, new.subject, new.sender, new.recipients, new.body_text);
					END;

					CREATE TRIGGER IF NOT EXISTS mails_ad AFTER DELETE ON mails BEGIN
						INSERT INTO mails_fts(mails_fts, rowid, subject, sender, recipients, body_text)
						VALUES ('delete', old.id, old.subject, old.sender, old.recipients, old.body_text);
					END;

					CREATE TRIGGER IF NOT EXISTS mails_au AFTER UPDATE ON mails BEGIN
						INSERT INTO mails_fts(mails_fts, rowid, subject, sender, recipients, body_text)
						VALUES ('delete', old.id, old.subject, old.sender, old.recipients, old.body_text);
						INSERT INTO mails_fts(rowid, subject, sender, recipients, body_text)
						VALUES (new.id, new.subject, new.sender, new.recipients, new.body_text);
					END;
					"""
				)

				connection.execute(
					"""
					INSERT OR REPLACE INTO mails_fts(rowid, subject, sender, recipients, body_text)
					SELECT id, subject, sender, recipients, body_text
					FROM mails
					"""
				)
			except sqlite3.OperationalError:
				# Fallback automatique si FTS5 est indisponible.
				pass

	def upsert_mail(self, mail: MailRecord) -> int:
		now_iso = datetime.now(UTC).isoformat()

		with self._connect() as connection:
			cursor = connection.execute(
				"""
				INSERT INTO mails (
					uid,
					message_id,
					folder,
					subject,
					sender,
					recipients,
					sent_at,
					body_text,
					body_size,
					attachment_count,
					created_at,
					updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				ON CONFLICT(uid, folder) DO UPDATE SET
					message_id = excluded.message_id,
					subject = excluded.subject,
					sender = excluded.sender,
					recipients = excluded.recipients,
					sent_at = excluded.sent_at,
					body_text = excluded.body_text,
					body_size = excluded.body_size,
					attachment_count = excluded.attachment_count,
					updated_at = excluded.updated_at
				""",
				(
					mail.uid,
					mail.message_id,
					mail.folder,
					mail.subject,
					mail.sender,
					mail.recipients,
					mail.date,
					mail.body_text,
					mail.body_size,
					mail.attachment_count,
					now_iso,
					now_iso,
				),
			)

			mail_id = cursor.lastrowid
			if not mail_id:
				row = connection.execute(
					"SELECT id FROM mails WHERE uid = ? AND folder = ?",
					(mail.uid, mail.folder),
				).fetchone()
				if row is None:
					raise RuntimeError("Impossible de recuperer l'identifiant du mail.")
				mail_id = int(row["id"])

			return int(mail_id)

	def replace_attachments(self, mail_id: int, attachments: list[AttachmentRecord]) -> None:
		now_iso = datetime.now(UTC).isoformat()

		with self._connect() as connection:
			connection.execute("DELETE FROM attachments WHERE mail_id = ?", (mail_id,))
			connection.executemany(
				"""
				INSERT INTO attachments (
					mail_id,
					filename,
					content_type,
					size_bytes,
					extracted_text,
					created_at
				) VALUES (?, ?, ?, ?, ?, ?)
				""",
				[
					(
						mail_id,
						attachment.filename,
						attachment.content_type,
						attachment.size_bytes,
						attachment.extracted_text,
						now_iso,
					)
					for attachment in attachments
				],
			)

	def replace_entities(self, mail_id: int, entities: list[EntityRecord]) -> None:
		now_iso = datetime.now(UTC).isoformat()

		with self._connect() as connection:
			connection.execute("DELETE FROM entities WHERE mail_id = ?", (mail_id,))
			connection.executemany(
				"""
				INSERT INTO entities (
					mail_id,
					entity_type,
					entity_value,
					confidence,
					source,
					created_at
				) VALUES (?, ?, ?, ?, ?, ?)
				""",
				[
					(
						mail_id,
						entity.entity_type,
						entity.entity_value,
						entity.confidence,
						entity.source,
						now_iso,
					)
					for entity in entities
				],
			)

	def get_recent_mails(self, limit: int = 10) -> list[dict[str, Any]]:
		with self._connect() as connection:
			rows = connection.execute(
				"""
				SELECT
					id,
					uid,
					folder,
					subject,
					sender,
					recipients,
					sent_at,
					body_size,
					attachment_count
				FROM mails
				ORDER BY datetime(sent_at) DESC
				LIMIT ?
				""",
				(limit,),
			).fetchall()
			return [dict(row) for row in rows]

	def get_all_mails(self) -> list[dict[str, Any]]:
		with self._connect() as connection:
			rows = connection.execute(
				"""
				SELECT
					id,
					uid,
					folder,
					subject,
					sender,
					recipients,
					sent_at,
					body_text,
					body_size,
					attachment_count
				FROM mails
				ORDER BY datetime(sent_at) DESC
				"""
			).fetchall()
			return [dict(row) for row in rows]

	def search_mails(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
		fts_results = self._search_mails_fts(query=query, limit=limit)
		if fts_results:
			return fts_results

		return self._search_mails_fallback(query=query, limit=limit)

	def _search_mails_fts(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
		tokens = _extract_search_tokens(query)
		if not tokens:
			return []

		fts_query = " OR ".join(f'"{token}"*' for token in tokens)

		with self._connect() as connection:
			try:
				rows = connection.execute(
					"""
					SELECT
						m.id,
						m.uid,
						m.folder,
						m.subject,
						m.sender,
						m.recipients,
						m.sent_at,
						m.body_size,
						m.attachment_count,
						bm25(mails_fts, 6.0, 3.0, 2.0, 1.0) AS score
					FROM mails_fts
					JOIN mails AS m ON m.id = mails_fts.rowid
					WHERE mails_fts MATCH ?
					ORDER BY score ASC, datetime(m.sent_at) DESC
					LIMIT ?
					""",
					(fts_query, limit),
				).fetchall()
			except sqlite3.OperationalError:
				return []

		return [dict(row) for row in rows]

	def _search_mails_fallback(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
		normalized_query = _normalize_text(query)
		if not normalized_query:
			return []

		tokens = _extract_search_tokens(query)
		if not tokens:
			return []

		matches: list[dict[str, Any]] = []
		for mail in self.get_all_mails():
			searchable_parts = [
				mail.get("subject", ""),
				mail.get("sender", ""),
				mail.get("recipients", ""),
				mail.get("body_text", ""),
			]
			searchable_text = _normalize_text(" ".join(str(part) for part in searchable_parts))

			score = sum(1 for token in tokens if token in searchable_text)
			if score > 0:
				mail_with_score = dict(mail)
				mail_with_score["score"] = score
				matches.append(mail_with_score)

		matches.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("sent_at", ""))), reverse=False)
		if not matches:
			return []

		required_score = 1 if len(tokens) <= 2 else 2
		filtered_matches = [item for item in matches if int(item.get("score", 0)) >= required_score]
		return filtered_matches[:limit]

	def get_mail_attachments(self, mail_id: int) -> list[dict[str, Any]]:
		with self._connect() as connection:
			rows = connection.execute(
				"""
				SELECT id, mail_id, filename, content_type, size_bytes, extracted_text
				FROM attachments
				WHERE mail_id = ?
				ORDER BY id ASC
				""",
				(mail_id,),
			).fetchall()
			return [dict(row) for row in rows]

	def get_mail_entities(self, mail_id: int) -> list[dict[str, Any]]:
		with self._connect() as connection:
			rows = connection.execute(
				"""
				SELECT id, mail_id, entity_type, entity_value, confidence, source
				FROM entities
				WHERE mail_id = ?
				ORDER BY id ASC
				""",
				(mail_id,),
			).fetchall()
			return [dict(row) for row in rows]

	def get_schema_overview(self) -> dict[str, str]:
		with self._connect() as connection:
			rows = connection.execute(
				"""
				SELECT name, sql
				FROM sqlite_master
				WHERE type = 'table'
				  AND name IN ('mails', 'attachments', 'entities')
				ORDER BY name
				"""
			).fetchall()
			return {str(row["name"]): str(row["sql"] or "") for row in rows}


def _normalize_text(value: str) -> str:
	normalized = unicodedata.normalize("NFKD", value)
	without_accents = "".join(character for character in normalized if not unicodedata.combining(character))
	return " ".join(without_accents.lower().split())


_SEARCH_STOPWORDS = {
	"a",
	"au",
	"aux",
	"avec",
	"ce",
	"ces",
	"de",
	"des",
	"du",
	"dans",
	"en",
	"et",
	"je",
	"la",
	"le",
	"les",
	"mes",
	"mon",
	"nos",
	"notre",
	"pour",
	"que",
	"qui",
	"sur",
	"ses",
	"son",
	"une",
	"un",
	"vos",
	"votre",
	"resume",
	"resumer",
	"echanges",
	"echanges",
	"echange",
	"derniers",
	"dernieres",
	"dernier",
	"derniere",
	"jours",
	"jour",
	"quinze",
}


def _extract_search_tokens(query: str) -> list[str]:
	normalized_query = _normalize_text(query)
	raw_tokens = re.findall(r"[a-z0-9_]+", normalized_query)
	return [token for token in raw_tokens if len(token) > 2 and token not in _SEARCH_STOPWORDS]
