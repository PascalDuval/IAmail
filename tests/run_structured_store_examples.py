from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.structured_store import (  # noqa: E402
    AttachmentRecord,
    EntityRecord,
    MailRecord,
    StructuredStore,
)


def _ok(label: str, ok: bool) -> bool:
    status = "OK" if ok else "KO"
    print(f"[{status}] {label}")
    return ok


def main() -> int:
    db_path = PROJECT_ROOT / "tests" / "samples" / "store_example.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    store = StructuredStore(db_path=db_path)
    store.init_schema()

    schema = store.get_schema_overview()
    all_ok = True
    all_ok = _ok("schema contient mails", "mails" in schema) and all_ok
    all_ok = _ok("schema contient attachments", "attachments" in schema) and all_ok
    all_ok = _ok("schema contient entities", "entities" in schema) and all_ok

    mail_id = store.upsert_mail(
        MailRecord(
            uid=101,
            folder="INBOX",
            subject="Devis toiture",
            sender="contact@example.com",
            recipients="lacsaplavud@gmail.com",
            date="2026-07-12T11:34:00+00:00",
            body_text="Bonjour, voici le devis en piece jointe.",
            body_size=41,
            attachment_count=1,
            message_id="<msg-101@example.com>",
        )
    )

    store.replace_attachments(
        mail_id,
        [
            AttachmentRecord(
                filename="devis.pdf",
                content_type="application/pdf",
                size_bytes=20513,
                extracted_text="Montant total 1234 EUR",
            )
        ],
    )

    store.replace_entities(
        mail_id,
        [
            EntityRecord(entity_type="amount", entity_value="1234 EUR", confidence=0.97),
            EntityRecord(entity_type="person", entity_value="Nam", confidence=0.72),
        ],
    )

    recent = store.get_recent_mails(limit=5)
    all_ok = _ok("lecture recent mails non vide", len(recent) > 0) and all_ok
    if recent:
        all_ok = _ok("lecture sujet correct", recent[0]["subject"] == "Devis toiture") and all_ok
        all_ok = _ok("lecture uid correct", int(recent[0]["uid"]) == 101) and all_ok

    if all_ok:
        print("Etape 4 OK: schema + insertion + lecture SQLite valides.")
        return 0

    print("Etape 4 KO: echec sur schema, insertion ou lecture.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
