from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .indexer import SemanticIndexer
from .mail_connector import MailConnector
from .structured_store import StructuredStore


@dataclass
class IngestionSummary:
    folder: str
    fetched: int
    stored: int
    chunks_indexed: int


class IngestionService:
    def __init__(self, connector: MailConnector, store: StructuredStore, indexer: SemanticIndexer) -> None:
        self.connector = connector
        self.store = store
        self.indexer = indexer

    @classmethod
    def from_env(
        cls,
        db_path: str | Path | None = None,
        chroma_path: str | Path | None = None,
        collection_name: str = "mail_chunks",
    ) -> "IngestionService":
        load_dotenv()

        connector = MailConnector.from_env()
        store = StructuredStore(db_path=db_path or Path("data/mail_ai.db"))
        store.init_schema()
        indexer = SemanticIndexer(
            persist_directory=chroma_path or Path("data/chroma_db"),
            collection_name=collection_name,
        )
        return cls(connector=connector, store=store, indexer=indexer)

    def sync_folder(self, folder: str = "INBOX", limit: int = 50) -> IngestionSummary:
        records = self.connector.fetch_latest_mail_records(limit=limit, folder=folder)
        stored_count = 0
        chunk_count = 0

        for record in records:
            mail_id = self.store.upsert_mail(record)
            chunk_count += self.indexer.index_document(
                doc_id=f"{record.folder}:{record.uid}",
                text=record.body_text or record.subject,
                metadata={
                    "folder": record.folder,
                    "uid": record.uid,
                    "subject": record.subject,
                    "sender": record.sender,
                    "recipients": record.recipients,
                    "mail_id": mail_id,
                },
            )
            stored_count += 1

        return IngestionSummary(
            folder=folder,
            fetched=len(records),
            stored=stored_count,
            chunks_indexed=chunk_count,
        )