from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from typing import Any, Iterable

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
    if isinstance(value, str):
        return value

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


class MailConnector:
    def __init__(self, host: str = "imap.gmail.com", folder: str = "INBOX") -> None:
        self.host = host
        self.folder = folder

    def _connect(self) -> IMAPClient:
        load_dotenv()

        gmail_address = os.getenv("GMAIL_ADDRESS", "").strip()
        gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip()

        if not gmail_address or not gmail_app_password:
            raise ValueError(
                "Variables manquantes: GMAIL_ADDRESS et GMAIL_APP_PASSWORD dans le fichier .env"
            )

        client = IMAPClient(self.host, ssl=True)
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
