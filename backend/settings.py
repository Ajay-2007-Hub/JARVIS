"""Local auto-start settings endpoints."""

import ipaddress
import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.security.approval import (
    ApprovalExpired,
    ApprovalManager,
    ApprovalNotFound,
    ApprovalNotPending,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIRECTORY = PROJECT_ROOT / "scripts"
logger = logging.getLogger("jarvis.settings")
router = APIRouter(prefix="/api/settings", tags=["settings"])
approvals_router = APIRouter(prefix="/api/approvals", tags=["approvals"])
approval_manager = ApprovalManager()


class AutoStartUpdate(BaseModel):
    enabled: bool


def _is_loopback(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def run_task_script(script_name: str) -> subprocess.CompletedProcess[str]:
    if script_name not in {
        "status_autostart.ps1",
        "register_autostart.ps1",
        "unregister_autostart.ps1",
    }:
        raise ValueError("Unsupported scheduled-task script")
    script_path = SCRIPTS_DIRECTORY / script_name
    if not script_path.is_file():
        raise FileNotFoundError(f"Scheduled-task script not found: {script_path}")
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )


def get_autostart_status() -> bool:
    result = run_task_script("status_autostart.ps1")
    for line in result.stdout.splitlines():
        if line.strip() == "enabled=true":
            return True
        if line.strip() == "enabled=false":
            return False
    raise ValueError("Auto-start status script returned no enabled value")


@router.get("/autostart")
def read_autostart(request: Request) -> dict[str, bool]:
    if not _is_loopback(request):
        raise HTTPException(status_code=403, detail="Local requests only")
    try:
        return {"enabled": get_autostart_status()}
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        logger.exception("Could not read auto-start status")
        raise HTTPException(
            status_code=503,
            detail="Could not read auto-start status",
        ) from error


@router.post("/autostart", status_code=status.HTTP_202_ACCEPTED)
def request_autostart_change(request: Request, body: AutoStartUpdate) -> dict[str, object]:
    if not _is_loopback(request):
        raise HTTPException(status_code=403, detail="Local requests only")
    script_name = (
        "register_autostart.ps1" if body.enabled else "unregister_autostart.ps1"
    )
    action = "enable_autostart" if body.enabled else "disable_autostart"
    description = (
        "Register JARVIS to start when the current user signs in."
        if body.enabled
        else "Remove JARVIS from the current user's sign-in startup."
    )
    approval = approval_manager.request(
        action=action,
        description=description,
        execute=lambda: run_task_script(script_name),
    )
    return {"approval": approval}


def _approval_error(error: Exception) -> HTTPException:
    if isinstance(error, ApprovalNotFound):
        return HTTPException(status_code=404, detail="Approval request not found")
    if isinstance(error, ApprovalExpired):
        return HTTPException(status_code=410, detail="Approval request expired")
    if isinstance(error, ApprovalNotPending):
        return HTTPException(status_code=409, detail="Approval request is no longer pending")
    return HTTPException(status_code=500, detail="Approval operation failed")


@approvals_router.get("")
def list_approvals(request: Request) -> dict[str, list[dict[str, str]]]:
    if not _is_loopback(request):
        raise HTTPException(status_code=403, detail="Local requests only")
    return {"pending": approval_manager.pending()}


@approvals_router.post("/{approval_id}/approve")
def approve_request(request: Request, approval_id: str) -> dict[str, dict[str, str]]:
    if not _is_loopback(request):
        raise HTTPException(status_code=403, detail="Local requests only")
    try:
        return {"approval": approval_manager.approve(approval_id)}
    except (ApprovalNotFound, ApprovalExpired, ApprovalNotPending) as error:
        raise _approval_error(error) from error
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        logger.exception("Approved action failed: id=%s", approval_id)
        raise HTTPException(status_code=503, detail="Approved action failed") from error


@approvals_router.post("/{approval_id}/deny")
def deny_request(request: Request, approval_id: str) -> dict[str, dict[str, str]]:
    if not _is_loopback(request):
        raise HTTPException(status_code=403, detail="Local requests only")
    try:
        return {"approval": approval_manager.deny(approval_id)}
    except (ApprovalNotFound, ApprovalExpired, ApprovalNotPending) as error:
        raise _approval_error(error) from error
