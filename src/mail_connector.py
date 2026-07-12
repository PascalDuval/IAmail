from __future__ import annotations

import os
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from typing import Any, Iterable

import certifi
from dotenv import load_dotenv
from imapclient import IMAPClient


@dataclass
class MailSummary:
    uid: int
    subject: str
    sender: str
    date: datetime | None


def _decode_mime_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")

    parts = decode_header(value)
    decoded_parts: list[str] = []
    for chunk, encoding in parts:
        if isinstance(chunk, bytes):
            decoded_parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
        else:
            decoded_parts.append(chunk)
    return "".join(decoded_parts).strip()


def _extract_sender(sender_item: Any) -> str:
    if sender_item is None:
        return "(inconnu)"

    name = _decode_mime_text(getattr(sender_item, "name", None))
    mailbox = _decode_mime_text(getattr(sender_item, "mailbox", None))
    host = _decode_mime_text(getattr(sender_item, "host", None))
    address = ""
    if mailbox and host:
        address = f"{mailbox}@{host}"
    elif mailbox:
        address = mailbox

    if name and address:
        return f"{name} <{address}>"
    if address:
        return address
    if name:
        return name
    return "(inconnu)"


def _get_payload_value(payload: dict[Any, Any], key: str) -> Any:
    if key in payload:
        return payload[key]
    bkey = key.encode("ascii")
    return payload.get(bkey)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class MailConnector:
    def __init__(
        self,
        host: str = "imap.gmail.com",
        folder: str = "INBOX",
        port: int = 993,
        use_ssl: bool = True,
    ) -> None:
        self.host = host
        self.folder = folder
        self.port = port
        self.use_ssl = use_ssl

    @classmethod
    def from_env(cls) -> "MailConnector":
        load_dotenv()

        host = os.getenv("IMAP_HOST", "imap.gmail.com").strip() or "imap.gmail.com"
        folder = os.getenv("IMAP_FOLDER", "INBOX").strip() or "INBOX"

        raw_port = os.getenv("IMAP_PORT", "993").strip()
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ValueError("IMAP_PORT doit etre un entier (ex: 993).") from exc

        use_ssl = _env_bool("IMAP_SSL", True)

        return cls(host=host, folder=folder, port=port, use_ssl=use_ssl)

    def _build_ssl_context(self, verify_ssl: bool) -> ssl.SSLContext:
        context = ssl.create_default_context(cafile=certifi.where())
        if not verify_ssl:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    def _connect(self) -> IMAPClient:
        load_dotenv()

        gmail_address = os.getenv("GMAIL_ADDRESS", "").strip()
        gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

        if not gmail_address or not gmail_app_password:
            raise ValueError(
                "Variables manquantes: GMAIL_ADDRESS et GMAIL_APP_PASSWORD (fichier .env)."
            )

        verify_ssl = _env_bool("IMAP_SSL_VERIFY", True)
        ssl_context = self._build_ssl_context(verify_ssl) if self.use_ssl else None

        client_kwargs: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "ssl": self.use_ssl,
        }
        if ssl_context is not None:
            client_kwargs["ssl_context"] = ssl_context

        try:
            client = IMAPClient(**client_kwargs)
        except TypeError:
            # Compatibilite defensive si une ancienne version d'imapclient ignore ssl_context.
            client_kwargs.pop("ssl_context", None)
            client = IMAPClient(**client_kwargs)

        client.login(gmail_address, gmail_app_password)
        return client

    def list_latest(self, limit: int = 10) -> list[MailSummary]:
        if limit <= 0:
            return []

        with self._connect() as client:
            client.select_folder(self.folder, readonly=True)
            uids = client.search(["ALL"])

            if not uids:
                return []

            latest_uids = sorted(uids)[-limit:]
            fetched = client.fetch(latest_uids, ["ENVELOPE"])

        return self._build_summaries(fetched, latest_uids)

    def _build_summaries(
        self, fetched: dict[Any, dict[Any, Any]], latest_uids: Iterable[int]
    ) -> list[MailSummary]:
        summaries: list[MailSummary] = []

        for uid in sorted(latest_uids, reverse=True):
            payload = fetched.get(uid, {})
            envelope = _get_payload_value(payload, "ENVELOPE")
            if envelope is None:
                continue

            subject = _decode_mime_text(getattr(envelope, "subject", None)) or "(sans objet)"
            sender_list = getattr(envelope, "from_", None) or []
            sender = _extract_sender(sender_list[0] if sender_list else None)
            date = getattr(envelope, "date", None)

            summaries.append(
                MailSummary(
                    uid=int(uid),
                    subject=subject,
                    sender=sender,
                    date=date,
                )
            )

        return summaries
