from __future__ import annotations

from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from .mail_connector import MailConnector

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
        min=1,
        max=200,
        help="Nombre de mails recents a afficher.",
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
    table.add_column("Corps (car)", style="magenta", justify="right")
    table.add_column("PJ", style="yellow", justify="right")
    table.add_column("Objet", style="white")

    for mail in messages:
        table.add_row(
            _format_date(mail.date),
            mail.sender,
            str(mail.body_size),
            str(mail.attachment_count),
            mail.subject,
        )

    console.print(table)


if __name__ == "__main__":
    app()
