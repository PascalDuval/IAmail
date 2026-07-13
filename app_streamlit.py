"""Interface web locale Streamlit pour consulter les mails en mode safe ou hybride experimental."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import streamlit as st

from src.query_engine import QueryEngine
from src.structured_store import StructuredStore

DEFAULT_DB_PATH = Path("data/mail_ai.db")


def _format_mail_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Date": row.get("sent_at", ""),
            "Expediteur": row.get("sender", ""),
            "Objet": row.get("subject", ""),
            "Corps (car)": row.get("body_size", 0),
            "PJ": row.get("attachment_count", 0),
        }
        for row in rows
    ]


def _load_recent_mails(db_path: Path, limit: int) -> list[dict[str, Any]]:
    store = StructuredStore(db_path=db_path)
    store.init_schema()
    return store.get_recent_mails(limit=limit)


def _ask_safe(db_path: Path, chroma_path: Path, question: str) -> str:
    engine = QueryEngine.from_env(
        db_path=db_path,
        chroma_path=chroma_path,
        enable_semantic=False,
        enable_llm=False,
    )
    return engine.ask(question).answer


def _ask_hybrid(db_path: Path, chroma_path: Path, question: str) -> str:
    engine = QueryEngine.from_env(
        db_path=db_path,
        chroma_path=chroma_path,
        enable_semantic=True,
        enable_llm=True,
    )
    return engine.ask(question).answer


def main() -> None:
    st.set_page_config(page_title="Mail IA Agent", page_icon="✉️", layout="wide")

    st.title("Mail IA Agent")
    st.caption("Interface locale en mode safe par défaut: SQLite uniquement. Le mode hybride est expérimental.")

    with st.sidebar:
        st.header("Paramètres")
        db_path_value = st.text_input("Base SQLite", value=str(DEFAULT_DB_PATH))
        chroma_path_value = st.text_input("Dossier Chroma", value="data/chroma_db")
        recent_limit = st.slider("Nombre de mails affichés", min_value=5, max_value=10000, value=50, step=5)
        mode = st.radio(
            "Mode de réponse",
            options=["safe", "hybride experimental"],
            index=0,
            help="safe = SQLite uniquement; hybride = Chroma/Ollama, à utiliser seulement sur une machine stable.",
        )
        question = st.text_area(
            "Question",
            value="Résumé des dernières offres d'emplois sur les derniers quinze jours",
            height=120,
        )

    db_path = Path(db_path_value)
    chroma_path = Path(chroma_path_value)

    tab_recent, tab_ask = st.tabs(["Derniers mails", "Question safe"])

    with tab_recent:
        st.subheader("INBOX / récents")
        try:
            recent_mails = _load_recent_mails(db_path, recent_limit)
        except Exception as exc:
            st.error(f"Impossible de lire la base SQLite: {exc}")
            return

        if not recent_mails:
            st.info("Aucun mail trouvé dans la base locale.")
        else:
            st.dataframe(_format_mail_table(recent_mails), use_container_width=True, hide_index=True)

    with tab_ask:
        if mode == "safe":
            st.subheader("Réponse locale safe")
            st.warning("Ce mode n'utilise ni Chroma ni Ollama. Il évite les plantages liés au chemin hybride.")
        else:
            st.subheader("Réponse hybride expérimentale")
            st.error("Ce mode réactive Chroma/Ollama. Sur cette machine, il a déjà provoqué des coupures brutales. N'utilisez-le qu'à vos risques.")

        button_label = "Interroger en mode safe" if mode == "safe" else "Interroger en mode hybride"
        if st.button(button_label, type="primary"):
            if not question.strip():
                st.info("Entre une question avant d'interroger la base.")
            else:
                try:
                    if mode == "safe":
                        answer = _ask_safe(db_path=db_path, chroma_path=chroma_path, question=question)
                    else:
                        answer = _ask_hybrid(db_path=db_path, chroma_path=chroma_path, question=question)
                except Exception as exc:
                    st.error(f"Échec de l'interrogation: {exc}")
                else:
                    st.success(answer)


def launch() -> None:
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve())], check=False)


if __name__ == "__main__":
    main()
