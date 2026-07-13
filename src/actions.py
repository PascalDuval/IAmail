from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .mail_connector import MailConnector, MailOperationResult


@dataclass
class MailActionSummary:
	action: str
	uids: list[int]
	dry_run: bool
	message: str


class MailActions:
	def __init__(self, connector: MailConnector) -> None:
		self.connector = connector

	@classmethod
	def from_env(cls) -> "MailActions":
		return cls(connector=MailConnector.from_env())

	def archive(
		self,
		uids: Iterable[int],
		destination_folder: str = "Archive",
		source_folder: str = "INBOX",
		dry_run: bool = True,
	) -> MailActionSummary:
		result = self.connector.archive_uids(
			uids=list(uids),
			destination_folder=destination_folder,
			source_folder=source_folder,
			dry_run=dry_run,
		)
		return self._to_summary(result)

	def delete(
		self,
		uids: Iterable[int],
		source_folder: str = "INBOX",
		dry_run: bool = True,
	) -> MailActionSummary:
		result = self.connector.delete_uids(
			uids=list(uids),
			source_folder=source_folder,
			dry_run=dry_run,
		)
		return self._to_summary(result)

	def _to_summary(self, result: MailOperationResult) -> MailActionSummary:
		return MailActionSummary(
			action=result.action,
			uids=result.uids,
			dry_run=result.dry_run,
			message=result.message,
		)
