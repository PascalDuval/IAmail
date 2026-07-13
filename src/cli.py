from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .actions import MailActions
from .mail_connector import MailConnector
from .ingestion import IngestionService
from .query_engine import QueryEngine

app = typer.Typer(help="CLI du projet Mail IA Agent")
console = Console()


@app.callback()
def main() -> None:
    """Point d'entree CLI."""
    return None


def _format_date(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M")


@app.command()
def index(
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        min=5,
        max=10000,
        help="Nombre de mails recents a afficher (borne safe: 5 a 10000).",
    ),
) -> None:
    """Affiche les derniers mails de INBOX (date, expediteur, objet)."""
    connector = MailConnector.from_env()

    try:
        messages = connector.list_latest(limit=limit)
    except Exception as exc:
        console.print(f"[red]Erreur IMAP:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if not messages:
        console.print("[yellow]Aucun mail trouve dans INBOX.[/yellow]")
        return

    table = Table(title=f"{len(messages)} dernier(s) mail(s) INBOX")
    table.add_column("Date", style="cyan")
    table.add_column("Expediteur", style="green")
    table.add_column("Taille brute (octets)", style="magenta", justify="right")
    table.add_column("Objet", style="white")

    for mail in messages:
        table.add_row(
            _format_date(mail.date),
            mail.sender,
            str(mail.body_size),
            mail.subject,
        )

    console.print(table)


@app.command()
def sync(
    limit: int = typer.Option(
        50,
        "--limit",
        "-n",
        min=5,
        max=10000,
        help="Nombre de mails les plus recents a ingerer (borne safe: 5 a 10000).",
    ),
    folder: str = typer.Option("INBOX", "--folder", "-f", help="Dossier Gmail à synchroniser."),
    enable_indexing: bool = typer.Option(
        False,
        "--enable-indexing/--no-enable-indexing",
        help="Active l'indexation Chroma/Ollama. Desactive par defaut pour un mode safe (SQLite uniquement). Chemin experimental a n'utiliser que sur une machine stable.",
    ),
    db_path: Path = typer.Option(Path("data/mail_ai.db"), "--db-path", help="Chemin de la base SQLite locale."),
    chroma_path: Path = typer.Option(Path("data/chroma_db"), "--chroma-path", help="Chemin de persistence Chroma."),
) -> None:
    """Synchronise la boîte principale vers SQLite en mode safe par défaut, avec indexation optionnelle."""
    service = IngestionService.from_env(
        db_path=db_path,
        chroma_path=chroma_path,
        enable_indexing=enable_indexing,
    )

    try:
        summary = service.sync_folder(folder=folder, limit=limit, enable_indexing=enable_indexing)
    except Exception as exc:
        console.print(f"[red]Erreur lors de la synchronisation:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Boîte synchronisée:[/green] {summary.folder}")
    console.print(f"[green]Mails récupérés:[/green] {summary.fetched}")
    console.print(f"[green]Mails enregistrés:[/green] {summary.stored}")
    console.print(f"[green]Chunks indexés:[/green] {summary.chunks_indexed}")
    if not enable_indexing:
        console.print("[yellow]Mode safe actif:[/yellow] indexation Chroma/Ollama desactivee.")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question en francais a poser au moteur."),
    safe: bool = typer.Option(
        True,
        "--safe/--no-safe",
        help="Mode de secours SQLite-only par defaut. --no-safe active le chemin hybride experimental, a eviter si la machine plante.",
    ),
    db_path: Path = typer.Option(Path("data/mail_ai.db"), "--db-path", help="Chemin de la base SQLite locale."),
    chroma_path: Path = typer.Option(Path("data/chroma_db"), "--chroma-path", help="Chemin de persistence Chroma."),
) -> None:
    """Interroge SQLite en mode safe par défaut; le chemin hybride reste optionnel et experimental."""
    engine = QueryEngine.from_env(
        db_path=db_path,
        chroma_path=chroma_path,
        enable_semantic=not safe,
        enable_llm=not safe,
    )

    try:
        result = engine.ask(question)
    except Exception as exc:
        console.print(f"[red]Erreur lors de la requete:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print("[bold cyan]Question :[/bold cyan]", question)
    if safe:
        console.print("[yellow]Mode safe actif:[/yellow] aucune connexion Chroma/Ollama n'a ete utilisee.")
    console.print("[bold green]Réponse :[/bold green]", result.answer)


def _confirm_destructive_action(message: str, confirm: bool) -> None:
    if confirm:
        return
    if not typer.confirm(message, default=False):
        raise typer.Abort()


@app.command()
def archive(
    uids: list[int] = typer.Argument(..., help="UID(s) du ou des mails à archiver."),
    destination_folder: str = typer.Option("Archive", "--destination-folder", "-d", help="Dossier Gmail de destination."),
    source_folder: str = typer.Option("INBOX", "--source-folder", "-s", help="Dossier Gmail source."),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Simulation par défaut."),
    confirm: bool = typer.Option(False, "--confirm", help="Confirme explicitement l'exécution réelle."),
) -> None:
    """Archive un ou plusieurs mails après confirmation explicite."""
    actions = MailActions.from_env()

    if dry_run:
        summary = actions.archive(uids=uids, destination_folder=destination_folder, source_folder=source_folder, dry_run=True)
        console.print(f"[yellow]{summary.message}[/yellow]")
        return

    _confirm_destructive_action(
        f"Confirmez-vous l'archivage des UID {uids} vers {destination_folder} ?",
        confirm=confirm,
    )
    summary = actions.archive(uids=uids, destination_folder=destination_folder, source_folder=source_folder, dry_run=False)
    console.print(f"[green]{summary.message}[/green]")


@app.command()
def delete(
    uids: list[int] = typer.Argument(..., help="UID(s) du ou des mails à supprimer."),
    source_folder: str = typer.Option("INBOX", "--source-folder", "-s", help="Dossier Gmail source."),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Simulation par défaut."),
    confirm: bool = typer.Option(False, "--confirm", help="Confirme explicitement l'exécution réelle."),
) -> None:
    """Supprime un ou plusieurs mails après confirmation explicite."""
    actions = MailActions.from_env()

    if dry_run:
        summary = actions.delete(uids=uids, source_folder=source_folder, dry_run=True)
        console.print(f"[yellow]{summary.message}[/yellow]")
        return

    _confirm_destructive_action(
        f"Confirmez-vous la suppression définitive des UID {uids} depuis {source_folder} ?",
        confirm=confirm,
    )
    summary = actions.delete(uids=uids, source_folder=source_folder, dry_run=False)
    console.print(f"[red]{summary.message}[/red]")


if __name__ == "__main__":
    app()


def main() -> None:
    app()
