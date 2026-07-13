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


def _ask_hybrid(db_path: Path, chroma_path: Path, question: str, semantic_backend: str) -> str:
    engine = QueryEngine.from_env(
        db_path=db_path,
        chroma_path=chroma_path,
        enable_semantic=True,
        enable_llm=True,
        semantic_backend=semantic_backend,
    )
    return engine.ask(question).answer


def _split_answer_lines(answer: str) -> tuple[list[str], list[str]]:
    headline_lines: list[str] = []
    detail_lines: list[str] = []
    for raw_line in answer.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("-") or line.lower().startswith("dernieres alertes"):
            detail_lines.append(line)
            continue
        headline_lines.append(line)
    return headline_lines, detail_lines


def _render_answer(answer: str, mode: str) -> None:
    headline_lines, detail_lines = _split_answer_lines(answer)

    if mode == "safe":
        st.markdown("### Synthese")
    else:
        st.markdown("### Reponse")

    if headline_lines:
        st.info("\n\n".join(headline_lines))
    else:
        st.info(answer)

    if detail_lines:
        with st.expander("Details des alertes (optionnel)", expanded=False):
            for line in detail_lines:
                st.write(line)


def main() -> None:
    st.set_page_config(page_title="Mail IA Agent", page_icon="✉️", layout="wide")

    if "last_answer" not in st.session_state:
        st.session_state["last_answer"] = ""
    if "last_error" not in st.session_state:
        st.session_state["last_error"] = ""
    if "last_mode" not in st.session_state:
        st.session_state["last_mode"] = ""
    if "last_question" not in st.session_state:
        st.session_state["last_question"] = ""
    if "last_backend" not in st.session_state:
        st.session_state["last_backend"] = ""
    if "last_db_path" not in st.session_state:
        st.session_state["last_db_path"] = ""
    if "last_chroma_path" not in st.session_state:
        st.session_state["last_chroma_path"] = ""
    if "question_value" not in st.session_state:
        st.session_state["question_value"] = "Résumé des dernières offres d'emplois sur les derniers quinze jours"
    if "last_execution_label" not in st.session_state:
        st.session_state["last_execution_label"] = ""

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
        hybrid_backend = st.selectbox(
            "Backend hybride",
            options=["sqlite-vector", "chroma"],
            index=0,
            help="sqlite-vector = Ollama + index vectoriel dans SQLite (recommande). chroma = historique/experimental.",
        )

    db_path = Path(db_path_value)
    chroma_path = Path(chroma_path_value)

    tab_recent, tab_ask = st.tabs(["Derniers mails", "Question"])

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
        question = st.text_input(
            "Question",
            key="question_value",
            help="Appuie sur Entree pour relancer la recherche.",
        )

        if mode == "safe":
            st.subheader("Réponse locale safe")
            st.warning("Ce mode n'utilise ni Chroma ni Ollama. Il évite les plantages liés au chemin hybride.")
            st.caption("En mode safe, la réponse se met à jour automatiquement quand la question change.")
            st.caption("Backend actif: SQLite (safe)")
        else:
            st.subheader("Réponse hybride expérimentale")
            st.caption(f"Backend hybride selectionne: {hybrid_backend}")
            if hybrid_backend == "chroma":
                st.error("Mode hybride + Chroma: risque élevé sur cette machine (coupures déjà observées).")
            else:
                st.warning("Mode hybride + sqlite-vector: plus léger que Chroma, mais reste expérimental sur cette machine.")

        normalized_question = question.strip()
        safe_question_changed = (
            mode == "safe"
            and bool(normalized_question)
            and (
                st.session_state["last_question"] != normalized_question
                or st.session_state["last_mode"] != "safe"
                or st.session_state["last_db_path"] != str(db_path)
                or st.session_state["last_chroma_path"] != str(chroma_path)
            )
        )

        if safe_question_changed:
            with st.spinner("Analyse locale safe en cours..."):
                try:
                    answer = _ask_safe(db_path=db_path, chroma_path=chroma_path, question=normalized_question)
                except Exception as exc:
                    st.session_state["last_error"] = f"Échec de l'interrogation: {exc}"
                    st.session_state["last_answer"] = ""
                    st.session_state["last_mode"] = "safe"
                    st.session_state["last_question"] = normalized_question
                    st.session_state["last_backend"] = "sqlite-safe"
                    st.session_state["last_db_path"] = str(db_path)
                    st.session_state["last_chroma_path"] = str(chroma_path)
                    st.session_state["last_execution_label"] = "safe + SQLite"
                    st.error(st.session_state["last_error"])
                else:
                    st.session_state["last_error"] = ""
                    st.session_state["last_answer"] = answer
                    st.session_state["last_mode"] = "safe"
                    st.session_state["last_question"] = normalized_question
                    st.session_state["last_backend"] = "sqlite-safe"
                    st.session_state["last_db_path"] = str(db_path)
                    st.session_state["last_chroma_path"] = str(chroma_path)
                    st.session_state["last_execution_label"] = "safe + SQLite"
                    _render_answer(answer=answer, mode="safe")

        if mode == "hybride experimental":
            if st.button("Interroger en mode hybride", type="primary"):
                if not normalized_question:
                    st.info("Entre une question avant d'interroger la base.")
                else:
                    with st.spinner("Interrogation hybride en cours..."):
                        try:
                            answer = _ask_hybrid(
                                db_path=db_path,
                                chroma_path=chroma_path,
                                question=normalized_question,
                                semantic_backend=hybrid_backend,
                            )
                        except Exception as exc:
                            st.session_state["last_error"] = (
                                f"Échec de l'interrogation hybride (backend={hybrid_backend}): {exc}"
                            )
                            st.session_state["last_answer"] = ""
                            st.session_state["last_mode"] = "hybride experimental"
                            st.session_state["last_question"] = normalized_question
                            st.session_state["last_backend"] = hybrid_backend
                            st.session_state["last_db_path"] = str(db_path)
                            st.session_state["last_chroma_path"] = str(chroma_path)
                            st.session_state["last_execution_label"] = f"hybride + {hybrid_backend}"
                        else:
                            st.session_state["last_error"] = ""
                            st.session_state["last_answer"] = answer
                            st.session_state["last_mode"] = "hybride experimental"
                            st.session_state["last_question"] = normalized_question
                            st.session_state["last_backend"] = hybrid_backend
                            st.session_state["last_db_path"] = str(db_path)
                            st.session_state["last_chroma_path"] = str(chroma_path)
                            st.session_state["last_execution_label"] = f"hybride + {hybrid_backend}"

        if st.session_state["last_execution_label"]:
            st.caption(f"Derniere execution: {st.session_state['last_execution_label']}")

        if not normalized_question:
            st.info("Entre une question pour afficher une réponse.")
        elif st.session_state["last_error"] and st.session_state["last_question"] == normalized_question and st.session_state["last_mode"] == mode:
            st.error(st.session_state["last_error"])
        elif (
            st.session_state["last_answer"]
            and st.session_state["last_question"] == normalized_question
            and st.session_state["last_mode"] == mode
            and (
                mode == "safe"
                or st.session_state["last_backend"] == hybrid_backend
            )
        ):
            _render_answer(answer=st.session_state["last_answer"], mode=mode)
        elif mode == "hybride experimental":
            st.info("Clique sur 'Interroger en mode hybride' pour lancer la requête.")


def launch() -> None:
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(Path(__file__).resolve())], check=False)


if __name__ == "__main__":
    main()
