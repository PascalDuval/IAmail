from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion import IngestionService  # noqa: E402
from src.mail_connector import MailConnector  # noqa: E402
from src.structured_store import MailRecord, StructuredStore  # noqa: E402


class FakeConnector(MailConnector):
    def __init__(self) -> None:
        pass

    def fetch_latest_mail_records(self, limit: int = 50, folder: str = "INBOX"):
        body_one = "Le prix du gâteau au chocolat est passé de 22 EUR à 28 EUR."
        body_two = "Julien confirme le résumé des interactions et envoie le compte rendu."
        return [
            MailRecord(
                uid=9001,
                folder=folder,
                subject="Historique prix gâteau chocolat",
                sender="nam@example.com",
                recipients="client@example.com",
                date="2026-07-13T09:00:00+00:00",
                body_text=body_one,
                body_size=len(body_one),
                attachment_count=0,
                message_id="<sync-9001@example.com>",
            ),
            MailRecord(
                uid=9002,
                folder=folder,
                subject="Résumé interactions avec Julien",
                sender="julien@example.com",
                recipients="client@example.com",
                date="2026-07-13T10:00:00+00:00",
                body_text=body_two,
                body_size=len(body_two),
                attachment_count=0,
                message_id="<sync-9002@example.com>",
            ),
        ][:limit]


def _ok(label: str, ok: bool) -> bool:
    status = "OK" if ok else "KO"
    print(f"[{status}] {label}")
    return ok


def main() -> int:
    samples_dir = PROJECT_ROOT / "tests" / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    db_path = samples_dir / "sync_stage10.db"
    chroma_path = samples_dir / "sync_stage10_chroma"

    if db_path.exists():
        db_path.unlink()

    store = StructuredStore(db_path=db_path)
    store.init_schema()

    service = IngestionService(connector=FakeConnector(), store=store, indexer=None)
    summary = service.sync_folder(folder="INBOX", limit=2, enable_indexing=False)

    all_ok = True
    all_ok = _ok("mails récupérés", summary.fetched == 2) and all_ok
    all_ok = _ok("mails enregistrés", summary.stored == 2) and all_ok
    all_ok = _ok("chunks indexés", summary.chunks_indexed == 0) and all_ok
    all_ok = _ok("sqlite rempli", len(store.get_all_mails()) == 2) and all_ok

    if all_ok:
        print("Étape sync OK: synchronisation INBOX vers SQLite en mode safe valide.")
        return 0

    print("Étape sync KO: un élément de la synchronisation a échoué.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
