from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.indexer import SemanticIndexer  # noqa: E402
from src.llm import OllamaLLM  # noqa: E402
from src.query_engine import QueryEngine  # noqa: E402
from src.structured_store import MailRecord, StructuredStore  # noqa: E402


def _ok(label: str, ok: bool) -> bool:
    status = "OK" if ok else "KO"
    print(f"[{status}] {label}")
    return ok


def main() -> int:
    store_db = PROJECT_ROOT / "tests" / "samples" / "query_stage6.db"
    chroma_dir = PROJECT_ROOT / "tests" / "samples" / "query_stage6_chroma"

    if store_db.exists():
        store_db.unlink()

    store = StructuredStore(db_path=store_db)
    store.init_schema()

    indexer = SemanticIndexer(
        persist_directory=chroma_dir,
        collection_name="query_stage6_demo",
        chunk_size=220,
        chunk_overlap=30,
    )
    indexer.reset_collection()

    text = (
        "Bonjour Nam, le prix du gateau chocolat est passe de 22 EUR a 28 EUR entre mars et juin. "
        "Le nouveau devis reste valable jusqu'a vendredi."
    )

    mail_id = store.upsert_mail(
        MailRecord(
            uid=501,
            folder="INBOX",
            subject="Evolution prix gateau chocolat",
            sender="patisserie@example.com",
            recipients="client@example.com",
            date="2026-07-13T08:00:00+00:00",
            body_text=text,
            body_size=len(text),
            attachment_count=0,
            message_id="<query-501@example.com>",
        )
    )

    indexed_chunks = indexer.index_document(
        doc_id="mail_501",
        text=text,
        metadata={"source": "mail", "subject": "Evolution prix gateau chocolat", "mail_id": mail_id},
    )

    engine = QueryEngine(store=store, indexer=indexer, llm=OllamaLLM.from_env())
    result = engine.ask("Quel est le prix du gateau chocolat ?")

    all_ok = True
    all_ok = _ok("mails indexes", mail_id > 0) and all_ok
    all_ok = _ok("chunks indexes", indexed_chunks > 0) and all_ok
    all_ok = _ok("hits structurels disponibles", len(result.structured_hits) > 0) and all_ok
    all_ok = _ok("hits semantiques disponibles", len(result.semantic_hits) > 0) and all_ok
    all_ok = _ok("reponse non vide", bool(result.answer.strip())) and all_ok

    answer_lower = result.answer.lower()
    relevant_answer = ("28" in answer_lower) or ("gateau" in answer_lower) or ("chocolat" in answer_lower)
    all_ok = _ok("reponse pertinente", relevant_answer) and all_ok

    print("--- Reponse ---")
    print(result.answer)

    if all_ok:
        print("Etape 6-7 OK: wrapper LLM + query engine valides.")
        return 0

    print("Etape 6-7 KO: le moteur de requete n'a pas fourni de resultat satisfaisant.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
