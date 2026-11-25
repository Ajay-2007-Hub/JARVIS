"""In-memory approval manager for sensitive local actions."""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

logger = logging.getLogger("jarvis.security.approval")


class ApprovalError(Exception):
    """Base error for approval state transitions."""


class ApprovalNotFound(ApprovalError):
    """Raised when an approval identifier is unknown."""


class ApprovalExpired(ApprovalError):
    """Raised when an approval has expired."""


class ApprovalNotPending(ApprovalError):
    """Raised when an approval is no longer pending."""


@dataclass
class _Approval:
    id: str
    action: str
    description: str
    expires_at: datetime
    execute: Callable[[], None] = field(repr=False)
    status: str = "pending"

    def public_data(self) -> dict[str, str]:
        return {
            "id": self.id,
            "action": self.action,
            "description": self.description,
            "expires_at": self.expires_at.isoformat(),
            "status": self.status,
        }


class ApprovalManager:
    """Track requests and run their callback only after approval."""

    def __init__(self, expiry_seconds: int = 60) -> None:
        self._expiry_seconds = expiry_seconds
        self._requests: dict[str, _Approval] = {}
        self._lock = threading.Lock()

    def request(
        self,
        action: str,
        description: str,
        execute: Callable[[], None],
    ) -> dict[str, str]:
        approval = _Approval(
            id=str(uuid.uuid4()),
            action=action,
            description=description,
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=self._expiry_seconds),
            execute=execute,
        )
        with self._lock:
            self._requests[approval.id] = approval
        logger.info(
            "Approval requested: id=%s action=%s description=%s",
            approval.id,
            action,
            description,
        )
        return approval.public_data()

    def pending(self) -> list[dict[str, str]]:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._expire_pending(now)
            return [
                request.public_data()
                for request in self._requests.values()
                if request.status == "pending"
            ]

    def approve(self, approval_id: str) -> dict[str, str]:
        with self._lock:
            approval = self._get_pending(approval_id)
            approval.status = "approved"
            execute = approval.execute
        logger.info("Approval approved: id=%s action=%s", approval_id, approval.action)
        execute()
        return approval.public_data()

    def deny(self, approval_id: str) -> dict[str, str]:
        with self._lock:
            approval = self._get_pending(approval_id)
            approval.status = "denied"
        logger.info("Approval denied: id=%s action=%s", approval_id, approval.action)
        return approval.public_data()

    def _get_pending(self, approval_id: str) -> _Approval:
        approval = self._requests.get(approval_id)
        if approval is None:
            raise ApprovalNotFound(approval_id)
        if approval.status != "pending":
            raise ApprovalNotPending(approval_id)
        if approval.expires_at <= datetime.now(timezone.utc):
            approval.status = "expired"
            logger.info("Approval expired: id=%s action=%s", approval_id, approval.action)
            raise ApprovalExpired(approval_id)
        return approval

    def _expire_pending(self, now: datetime) -> None:
        for approval in self._requests.values():
            if approval.status == "pending" and approval.expires_at <= now:
                approval.status = "expired"
                logger.info(
                    "Approval expired: id=%s action=%s",
                    approval.id,
                    approval.action,
                )
