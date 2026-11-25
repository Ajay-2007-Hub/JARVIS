import pytest

from backend.security.approval import (
    ApprovalExpired,
    ApprovalManager,
    ApprovalNotFound,
    ApprovalNotPending,
)


def test_action_runs_only_after_approval() -> None:
    executed: list[str] = []
    manager = ApprovalManager()

    approval = manager.request(
        "test_action",
        "A test sensitive action",
        lambda: executed.append("ran"),
    )
    assert executed == []
    assert manager.pending()[0]["id"] == approval["id"]

    result = manager.approve(approval["id"])

    assert executed == ["ran"]
    assert result["status"] == "approved"
    assert manager.pending() == []


def test_denied_action_never_runs() -> None:
    executed: list[str] = []
    manager = ApprovalManager()
    approval = manager.request("test_action", "Deny me", lambda: executed.append("ran"))

    result = manager.deny(approval["id"])

    assert executed == []
    assert result["status"] == "denied"
    assert manager.pending() == []


def test_expired_action_cannot_be_approved() -> None:
    manager = ApprovalManager(expiry_seconds=0)
    approval = manager.request("test_action", "Expired", lambda: None)

    with pytest.raises(ApprovalExpired):
        manager.approve(approval["id"])
    assert manager.pending() == []


def test_unknown_and_already_decided_requests_are_rejected() -> None:
    manager = ApprovalManager()
    approval = manager.request("test_action", "One time", lambda: None)

    with pytest.raises(ApprovalNotFound):
        manager.approve("unknown")

    manager.deny(approval["id"])
    with pytest.raises(ApprovalNotPending):
        manager.approve(approval["id"])
