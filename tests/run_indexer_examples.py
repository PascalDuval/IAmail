from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.indexer import SemanticIndexer


def _ok(label: str, ok: bool) -> bool:
    status = "OK" if ok else "KO"
    print(f"[{status}] {label}")
    return ok


def main() -> int:
    persist_dir = PROJECT_ROOT / "tests" / "samples" / "chroma_stage5"

    indexer = SemanticIndexer(
        persist_directory=persist_dir,
        collection_name="stage5_demo",
        chunk_size=220,
        chunk_overlap=30,
    )
    indexer.reset_collection()

    indexed_count = 0
    indexed_count += indexer.index_document(
        doc_id="mail_001",
        text=(
            "Message de Nam: Le prix du gateau au chocolat est passe de 22 EUR a 28 EUR "
            "entre mars et juin. Pense a comparer avec les autres devis."
        ),
        metadata={"source": "mail", "subject": "Evolution prix gateau chocolat"},
    )
    indexed_count += indexer.index_document(
        doc_id="mail_002",
        text=(
            "Conversation avec Julie sur la location de salle. Budget prevu: 900 EUR. "
            "Aucune mention du gateau ici."
        ),
        metadata={"source": "mail", "subject": "Budget salle"},
    )
    indexed_count += indexer.index_document(
        doc_id="mail_003",
        text=(
            "Recap de commande patisserie: gateau chocolat, gateau framboise et gateau citron. "
            "Le gateau chocolat reste le plus demande."
        ),
        metadata={"source": "mail", "subject": "Commande patisserie"},
    )

    all_ok = True
    all_ok = _ok("documents indexes", indexed_count >= 3) and all_ok
    all_ok = _ok("chunks persistes dans Chroma", indexer.count() >= 3) and all_ok

    results = indexer.semantic_search("prix du gateau chocolat", n_results=3)
    all_ok = _ok("requete semantique retourne des resultats", len(results) > 0) and all_ok

    top_text = (results[0].get("document") or "").lower() if results else ""
    top_has_signal = ("gateau" in top_text) or ("chocolat" in top_text)
    all_ok = _ok("top resultat semantiquement pertinent", top_has_signal) and all_ok

    if all_ok:
        print("Etape 5 OK: chunking + embeddings + persistance Chroma + requete semantique valides.")
        return 0

    print("Etape 5 KO: la validation semantique a echoue.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
