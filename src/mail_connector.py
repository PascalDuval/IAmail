from __future__ import annotations

import os
import ssl
from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from typing import Any, Iterable

import certifi
from dotenv import load_dotenv
from imapclient import IMAPClient

from .structured_store import MailRecord


MAX_SAFE_FETCH_LIMIT = 10_000
DEFAULT_FETCH_BATCH_SIZE = 200


@dataclass
class MailSummary:
    uid: int
    subject: str
    sender: str
    date: datetime | None
    body_size: int
    attachment_count: int


@dataclass
class MailOperationResult:
    action: str
    uids: list[int]
    dry_run: bool
    folder: str
    destination_folder: str | None = None
    message: str = ""


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


def _extract_recipients(envelope: Any) -> str:
    recipient_parts: list[str] = []
    for field_name in ("to_", "cc", "bcc"):
        recipients = getattr(envelope, field_name, None) or []
        for recipient in recipients:
            name = _decode_mime_text(getattr(recipient, "name", None))
            mailbox = _decode_mime_text(getattr(recipient, "mailbox", None))
            host = _decode_mime_text(getattr(recipient, "host", None))

            address = ""
            if mailbox and host:
                address = f"{mailbox}@{host}"
            elif mailbox:
                address = mailbox

            if name and address:
                recipient_parts.append(f"{name} <{address}>")
            elif address:
                recipient_parts.append(address)
            elif name:
                recipient_parts.append(name)

    return ", ".join(dict.fromkeys(recipient_parts))


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


def _decode_text_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw_payload = part.get_payload()
        if isinstance(raw_payload, str):
            return raw_payload
        return ""

    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _extract_body_and_attachment_count(raw_message: bytes) -> tuple[str, int]:
    parsed = message_from_bytes(raw_message)
    text_chunks: list[str] = []
    attachment_count = 0

    for part in parsed.walk():
        content_type = part.get_content_type().lower()
        disposition = (part.get_content_disposition() or "").lower()
        filename = part.get_filename()

        if disposition == "attachment" or filename:
            attachment_count += 1
            continue

        if content_type == "text/plain" and disposition != "attachment":
            text = _decode_text_part(part).strip()
            if text:
                text_chunks.append(text)

    return "\n\n".join(text_chunks), attachment_count


def _get_first_payload_value(payload: dict[Any, Any], keys: list[str]) -> Any:
    for key in keys:
        value = _get_payload_value(payload, key)
        if value is not None:
            return value
    return None


def _extract_message_size(payload: dict[Any, Any]) -> int:
    raw_size = _get_first_payload_value(payload, ["RFC822.SIZE"])
    if raw_size is None:
        return 0
    try:
        return int(raw_size)
    except (TypeError, ValueError):
        return 0


def _iter_uid_batches(uids: list[int], batch_size: int) -> Iterable[list[int]]:
    safe_batch_size = max(1, int(batch_size))
    for start in range(0, len(uids), safe_batch_size):
        yield uids[start : start + safe_batch_size]


class MailConnector:
    def __init__(
        self,
        host: str = "imap.gmail.com",
        folder: str = "INBOX",
        port: int = 993,
        use_ssl: bool = True,
        fetch_batch_size: int = DEFAULT_FETCH_BATCH_SIZE,
    ) -> None:
        self.host = host
        self.folder = folder
        self.port = port
        self.use_ssl = use_ssl
        self.fetch_batch_size = max(1, int(fetch_batch_size))

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

        raw_batch_size = os.getenv("IMAP_FETCH_BATCH_SIZE", str(DEFAULT_FETCH_BATCH_SIZE)).strip()
        try:
            fetch_batch_size = int(raw_batch_size)
        except ValueError as exc:
            raise ValueError("IMAP_FETCH_BATCH_SIZE doit etre un entier (ex: 200).") from exc

        return cls(
            host=host,
            folder=folder,
            port=port,
            use_ssl=use_ssl,
            fetch_batch_size=fetch_batch_size,
        )

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

    def _normalize_uids(self, uids: list[int] | tuple[int, ...] | set[int]) -> list[int]:
        normalized_uids = [int(uid) for uid in uids]
        if not normalized_uids:
            raise ValueError("Au moins un UID doit etre fourni.")
        return normalized_uids

    def _validate_limit(self, limit: int, min_limit: int = 1, max_limit: int = MAX_SAFE_FETCH_LIMIT) -> int:
        if limit < min_limit:
            raise ValueError(f"La limite doit etre comprise entre {min_limit} et {max_limit}.")
        if limit > max_limit:
            raise ValueError(
                f"Limite trop elevee ({limit}). Maximum autorise: {max_limit} pour un fetch IMAP safe."
            )
        return limit

    def _fetch_latest_uids(self, client: IMAPClient, folder: str, limit: int) -> list[int]:
        client.select_folder(folder, readonly=True)
        uids = client.search(["ALL"])
        if not uids:
            return []
        return sorted(uids)[-limit:]

    def _fetch_in_batches(self, client: IMAPClient, uids: list[int], data_items: list[str]) -> dict[Any, dict[Any, Any]]:
        fetched: dict[Any, dict[Any, Any]] = {}
        for uid_batch in _iter_uid_batches(uids, self.fetch_batch_size):
            batch_payload = client.fetch(uid_batch, data_items)
            fetched.update(batch_payload)
        return fetched

    def list_latest(self, limit: int = 10) -> list[MailSummary]:
        safe_limit = self._validate_limit(limit)

        with self._connect() as client:
            latest_uids = self._fetch_latest_uids(client, folder=self.folder, limit=safe_limit)
            if not latest_uids:
                return []
            # Fetch léger: en-têtes + taille brute, pour rester stable sur de gros volumes.
            fetched = self._fetch_in_batches(client, latest_uids, ["ENVELOPE", "RFC822.SIZE"])

        return self._build_summaries(fetched, latest_uids)

    def fetch_latest_mail_records(self, limit: int = 50, folder: str = "INBOX") -> list[MailRecord]:
        safe_limit = self._validate_limit(limit)
        records: list[MailRecord] = []

        with self._connect() as client:
            latest_uids = self._fetch_latest_uids(client, folder=folder, limit=safe_limit)
            if not latest_uids:
                return []

            ordered_uids = sorted(latest_uids, reverse=True)
            for uid_batch in _iter_uid_batches(ordered_uids, self.fetch_batch_size):
                fetched_batch = client.fetch(uid_batch, ["ENVELOPE", "BODY.PEEK[]", "RFC822.SIZE"])

                for uid in uid_batch:
                    payload = fetched_batch.get(uid, {})
                    envelope = _get_payload_value(payload, "ENVELOPE")
                    if envelope is None:
                        continue

                    raw_message = _get_first_payload_value(
                        payload,
                        ["BODY[]", "BODY.PEEK[]", "RFC822"],
                    )

                    body_text = ""
                    attachment_count = 0
                    if isinstance(raw_message, bytes):
                        body_text, attachment_count = _extract_body_and_attachment_count(raw_message)
                    body_size = len(body_text) if body_text else _extract_message_size(payload)

                    subject = _decode_mime_text(getattr(envelope, "subject", None)) or "(sans objet)"
                    sender_list = getattr(envelope, "from_", None) or []
                    sender = _extract_sender(sender_list[0] if sender_list else None)
                    recipients = _extract_recipients(envelope)
                    date_value = getattr(envelope, "date", None)
                    if isinstance(date_value, datetime):
                        date_string = date_value.isoformat()
                    else:
                        date_string = _decode_mime_text(date_value) or ""

                    records.append(
                        MailRecord(
                            uid=int(uid),
                            folder=folder,
                            subject=subject,
                            sender=sender,
                            recipients=recipients,
                            date=date_string,
                            body_text=body_text,
                            body_size=body_size,
                            attachment_count=attachment_count,
                            message_id=_decode_mime_text(getattr(envelope, "message_id", None)) or None,
                        )
                    )

        return records

    def archive_uids(
        self,
        uids: list[int] | tuple[int, ...] | set[int],
        destination_folder: str = "Archive",
        source_folder: str = "INBOX",
        dry_run: bool = True,
    ) -> MailOperationResult:
        normalized_uids = self._normalize_uids(uids)

        if dry_run:
            return MailOperationResult(
                action="archive",
                uids=normalized_uids,
                dry_run=True,
                folder=source_folder,
                destination_folder=destination_folder,
                message=f"Simulation: les mails {normalized_uids} seraient archives vers {destination_folder}.",
            )

        with self._connect() as client:
            client.select_folder(source_folder, readonly=False)
            try:
                client.create_folder(destination_folder)
            except Exception:
                pass

            if hasattr(client, "move"):
                client.move(normalized_uids, destination_folder)
            else:
                client.copy(normalized_uids, destination_folder)
                client.delete_messages(normalized_uids)
                client.expunge()

        return MailOperationResult(
            action="archive",
            uids=normalized_uids,
            dry_run=False,
            folder=source_folder,
            destination_folder=destination_folder,
            message=f"Mails {normalized_uids} archives vers {destination_folder}.",
        )

    def delete_uids(
        self,
        uids: list[int] | tuple[int, ...] | set[int],
        source_folder: str = "INBOX",
        dry_run: bool = True,
    ) -> MailOperationResult:
        normalized_uids = self._normalize_uids(uids)

        if dry_run:
            return MailOperationResult(
                action="delete",
                uids=normalized_uids,
                dry_run=True,
                folder=source_folder,
                message=f"Simulation: les mails {normalized_uids} seraient supprimes de {source_folder}.",
            )

        with self._connect() as client:
            client.select_folder(source_folder, readonly=False)
            client.delete_messages(normalized_uids)
            client.expunge()

        return MailOperationResult(
            action="delete",
            uids=normalized_uids,
            dry_run=False,
            folder=source_folder,
            message=f"Mails {normalized_uids} supprimes de {source_folder}.",
        )

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

            body_size = _extract_message_size(payload)

            summaries.append(
                MailSummary(
                    uid=int(uid),
                    subject=subject,
                    sender=sender,
                    date=date,
                    body_size=body_size,
                    attachment_count=0,
                )
            )

        return summaries
