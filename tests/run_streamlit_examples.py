from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app_streamlit import _ask_safe, _format_mail_table, _load_recent_mails  # noqa: E402
from src.structured_store import MailRecord, StructuredStore  # noqa: E402


def _ok(label: str, ok: bool) -> bool:
    status = "OK" if ok else "KO"
    print(f"[{status}] {label}")
    return ok


def main() -> int:
    samples_dir = PROJECT_ROOT / "tests" / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    db_path = samples_dir / "streamlit_stage10.db"
    if db_path.exists():
        db_path.unlink()

    store = StructuredStore(db_path=db_path)
    store.init_schema()

    body = (
        "Bonjour, voici le résumé des dernières offres d'emplois sur les quinze derniers jours. "
        "Nous avons publié trois postes nouveaux cette semaine."
    )
    store.upsert_mail(
        MailRecord(
            uid=8001,
            folder="INBOX",
            subject="Résumé offres d'emploi",
            sender="jobs@example.com",
            recipients="client@example.com",
            date="2026-07-13T11:00:00+00:00",
            body_text=body,
            body_size=len(body),
            attachment_count=0,
            message_id="<streamlit-8001@example.com>",
        )
    )

    recent_mails = _load_recent_mails(db_path=db_path, limit=5)
    rendered_rows = _format_mail_table(recent_mails)
    answer = _ask_safe(db_path=db_path, chroma_path=PROJECT_ROOT / "tests" / "samples" / "streamlit_stage10_chroma", question="Résumé des dernières offres d'emplois sur les derniers quinze jours")

    all_ok = True
    all_ok = _ok("mail chargé dans SQLite", len(recent_mails) == 1) and all_ok
    all_ok = _ok("table Streamlit générable", len(rendered_rows) == 1 and rendered_rows[0]["Objet"] == "Résumé offres d'emploi") and all_ok
    all_ok = _ok("réponse safe non vide", bool(answer.strip())) and all_ok
    all_ok = _ok("réponse safe ne mentionne pas Chroma", "Chroma" not in answer) and all_ok

    print("--- Réponse safe ---")
    print(answer)

    if all_ok:
        print("Étape 10-11 OK: interface Streamlit safe valide.")
        return 0

    print("Étape 10-11 KO: le flux Streamlit safe a échoué.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())