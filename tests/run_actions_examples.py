from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.actions import MailActions  # noqa: E402
from src.indexer import SemanticIndexer  # noqa: E402
from src.llm import OllamaLLM  # noqa: E402
from src.query_engine import QueryEngine  # noqa: E402
from src.structured_store import MailRecord, StructuredStore  # noqa: E402


class FakeMailConnector:
    def __init__(self) -> None:
        self.archive_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []

    def archive_uids(self, uids, destination_folder="Archive", source_folder="INBOX", dry_run=True):
        payload = {
            "uids": list(uids),
            "destination_folder": destination_folder,
            "source_folder": source_folder,
            "dry_run": dry_run,
        }
        self.archive_calls.append(payload)
        return type(
            "ArchiveResult",
            (),
            {
                "action": "archive",
                "uids": list(uids),
                "dry_run": dry_run,
                "message": f"{'Simulation' if dry_run else 'OK'} archive {list(uids)}",
            },
        )()

    def delete_uids(self, uids, source_folder="INBOX", dry_run=True):
        payload = {
            "uids": list(uids),
            "source_folder": source_folder,
            "dry_run": dry_run,
        }
        self.delete_calls.append(payload)
        return type(
            "DeleteResult",
            (),
            {
                "action": "delete",
                "uids": list(uids),
                "dry_run": dry_run,
                "message": f"{'Simulation' if dry_run else 'OK'} delete {list(uids)}",
            },
        )()


def _ok(label: str, ok: bool) -> bool:
    status = "OK" if ok else "KO"
    print(f"[{status}] {label}")
    return ok


def main() -> int:
    samples_dir = PROJECT_ROOT / "tests" / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    db_path = samples_dir / "stage8_actions.db"
    chroma_dir = samples_dir / "stage8_actions_chroma"
    if db_path.exists():
        db_path.unlink()

    store = StructuredStore(db_path=db_path)
    store.init_schema()
    indexer = SemanticIndexer(
        persist_directory=chroma_dir,
        collection_name="stage8_actions_demo",
        chunk_size=220,
        chunk_overlap=30,
    )
    indexer.reset_collection()

    text = (
        "Bonjour Julien, l'historique du prix du gâteau au chocolat montre une évolution de 22 EUR à 28 EUR. "
        "Merci pour le suivi."
    )

    store.upsert_mail(
        MailRecord(
            uid=701,
            folder="INBOX",
            subject="Historique prix gateau chocolat",
            sender="patisserie@example.com",
            recipients="client@example.com",
            date="2026-07-13T09:00:00+00:00",
            body_text=text,
            body_size=len(text),
            attachment_count=0,
            message_id="<stage8-701@example.com>",
        )
    )
    indexer.index_document(
        doc_id="mail_701",
        text=text,
        metadata={"source": "mail", "subject": "Historique prix gateau chocolat"},
    )

    engine = QueryEngine(store=store, indexer=indexer, llm=OllamaLLM.from_env())
    answer = engine.ask("Quel est l'historique du prix du gâteau au chocolat ?")

    fake_connector = FakeMailConnector()
    actions = MailActions(fake_connector)

    archive_dry = actions.archive([701], destination_folder="Archive-MailIA", dry_run=True)
    archive_real = actions.archive([701], destination_folder="Archive-MailIA", dry_run=False)
    delete_dry = actions.delete([701], dry_run=True)
    delete_real = actions.delete([701], dry_run=False)

    all_ok = True
    all_ok = _ok("ask renvoie une réponse pertinente", bool(answer.answer.strip())) and all_ok
    all_ok = _ok("ask mentionne le gateau ou le prix", any(token in answer.answer.lower() for token in ["gâteau", "gateau", "28", "22"])) and all_ok
    all_ok = _ok("archive en simulation fonctionne", archive_dry.dry_run is True) and all_ok
    all_ok = _ok("archive en mode réel simulé par faux connecteur fonctionne", archive_real.dry_run is False and len(fake_connector.archive_calls) >= 2) and all_ok
    all_ok = _ok("delete en simulation fonctionne", delete_dry.dry_run is True) and all_ok
    all_ok = _ok("delete en mode réel simulé par faux connecteur fonctionne", delete_real.dry_run is False and len(fake_connector.delete_calls) >= 2) and all_ok

    print("--- Réponse ask ---")
    print(answer.answer)

    if all_ok:
        print("Étapes 8-9 OK: ask + archive + delete valides.")
        return 0

    print("Étapes 8-9 KO: un des flux ask/archive/delete a échoué.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
