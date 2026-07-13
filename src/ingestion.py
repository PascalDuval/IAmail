from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .indexer import SemanticIndexer
from .mail_connector import MailConnector
from .sqlite_vector_indexer import SQLiteVectorIndexer
from .structured_store import StructuredStore


@dataclass
class IngestionSummary:
    folder: str
    fetched: int
    stored: int
    chunks_indexed: int


class IngestionService:
    def __init__(
        self,
        connector: MailConnector,
        store: StructuredStore,
        indexer: Any | None,
    ) -> None:
        self.connector = connector
        self.store = store
        self.indexer = indexer

    @classmethod
    def from_env(
        cls,
        db_path: str | Path | None = None,
        chroma_path: str | Path | None = None,
        collection_name: str = "mail_chunks",
        enable_indexing: bool = True,
        index_backend: str = "sqlite-vector",
    ) -> "IngestionService":
        load_dotenv()

        connector = MailConnector.from_env()
        store = StructuredStore(db_path=db_path or Path("data/mail_ai.db"))
        store.init_schema()
        selected_backend = (index_backend or os.getenv("INDEX_BACKEND", "sqlite-vector")).strip().lower()
        indexer: Any | None = None
        if enable_indexing:
            if selected_backend == "chroma":
                indexer = SemanticIndexer(
                    persist_directory=chroma_path or Path("data/chroma_db"),
                    collection_name=collection_name,
                )
            elif selected_backend == "sqlite-vector":
                indexer = SQLiteVectorIndexer(
                    db_path=store.db_path,
                    collection_name=collection_name,
                )
            else:
                raise ValueError(
                    f"Backend d'index inconnu: {selected_backend}. Utiliser 'sqlite-vector' ou 'chroma'."
                )
        return cls(connector=connector, store=store, indexer=indexer)

    def sync_folder(self, folder: str = "INBOX", limit: int = 50, enable_indexing: bool = True) -> IngestionSummary:
        records = self.connector.fetch_latest_mail_records(limit=limit, folder=folder)
        stored_count = 0
        chunk_count = 0
        should_index = enable_indexing and self.indexer is not None

        for record in records:
            mail_id = self.store.upsert_mail(record)
            if should_index:
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