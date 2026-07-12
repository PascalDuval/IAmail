from __future__ import annotations

import sqlite3
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
