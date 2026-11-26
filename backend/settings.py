"""Local auto-start settings endpoints."""

import ipaddress
import json
import logging
import subprocess
import threading
import time
from concurrent.futures import Future
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
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
STATUS_CACHE_SECONDS = 30
_status_cache: tuple[float, dict[str, bool | str | int]] | None = None
_status_cache_lock = threading.Lock()
_status_inflight: Future[dict[str, bool | str | int | None]] | None = None
_status_generation = 0


class AutostartStatusQueryError(Exception):
    def __init__(
        self,
        reason: str,
        stdout: str | bytes = "",
        stderr: str | bytes = "",
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.stdout = stdout
        self.stderr = stderr


class AutoStartUpdate(BaseModel):
    enabled: bool


def _hidden_startupinfo() -> subprocess.STARTUPINFO:
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo


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
            "-WindowStyle",
            "Hidden",
            "-File",
            str(script_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
        creationflags=CREATE_NO_WINDOW,
        startupinfo=_hidden_startupinfo(),
        shell=False,
    )


def _query_autostart_status() -> dict[str, bool | str | int]:
    script = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$t = Get-ScheduledTask -TaskName JARVIS -ErrorAction SilentlyContinue; "
        "if (-not $t) { '{\"registered\":false,\"enabled\":false}' } "
        "else { $i = Get-ScheduledTaskInfo -TaskName JARVIS; "
        "[pscustomobject]@{registered=$true; "
        "enabled=[bool]$t.Settings.Enabled; state=[string]$t.State; "
        "last_result=$i.LastTaskResult} | ConvertTo-Json -Compress }"
    )
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-Command",
        script,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=True,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=_hidden_startupinfo(),
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AutostartStatusQueryError(
            "Task Scheduler status query timed out",
            error.stdout or error.output or "",
            error.stderr or "",
        ) from error
    except Exception as error:
        raise AutostartStatusQueryError(
            "Task Scheduler status query failed",
            getattr(error, "stdout", None) or getattr(error, "output", None) or "",
            getattr(error, "stderr", None) or "",
        ) from error

    try:
        payload = json.loads(result.stdout.lstrip("\ufeff"))
    except (json.JSONDecodeError, TypeError) as error:
        raise AutostartStatusQueryError(
            "Invalid Task Scheduler status response",
            result.stdout,
            result.stderr,
        ) from error
    if not isinstance(payload, dict):
        raise AutostartStatusQueryError(
            "Invalid Task Scheduler status response",
            result.stdout,
            result.stderr,
        )

    registered = payload.get("registered")
    enabled = payload.get("enabled")
    if not isinstance(registered, bool) or not isinstance(enabled, bool):
        raise AutostartStatusQueryError(
            "Invalid Task Scheduler status response",
            result.stdout,
            result.stderr,
        )
    if not registered:
        return {
            "enabled": False,
            "registered": False,
            "state": "Not registered",
            "last_result": 0,
        }

    state = payload.get("state")
    last_result = payload.get("last_result")
    if (
        not isinstance(state, str)
        or not isinstance(last_result, int)
        or isinstance(last_result, bool)
    ):
        raise AutostartStatusQueryError(
            "Invalid Task Scheduler status response",
            result.stdout,
            result.stderr,
        )
    return {
        "enabled": enabled,
        "registered": True,
        "state": state,
        "last_result": last_result,
    }


def invalidate_autostart_status_cache() -> None:
    global _status_cache, _status_generation
    with _status_cache_lock:
        _status_cache = None
        _status_generation += 1


def get_autostart_status() -> dict[str, bool | str | int | None]:
    global _status_cache, _status_inflight
    with _status_cache_lock:
        now = time.monotonic()
        if _status_cache is not None and now < _status_cache[0]:
            return dict(_status_cache[1])
        if _status_inflight is None:
            _status_inflight = Future()
            query = _status_inflight
            query_owner = True
            query_generation = _status_generation
        else:
            query = _status_inflight
            query_owner = False
            query_generation = _status_generation

    if not query_owner:
        return dict(query.result())

    try:
        result = _query_autostart_status()
    except Exception as error:
        if isinstance(error, AutostartStatusQueryError):
            reason = error.reason
            stdout = error.stdout
            stderr = error.stderr
        else:
            reason = "Task Scheduler status query failed"
            stdout = (
                getattr(error, "stdout", None)
                or getattr(error, "output", None)
                or ""
            )
            stderr = getattr(error, "stderr", None) or ""
        logger.exception(
            "Could not read auto-start status: stdout=%r stderr=%r",
            stdout,
            stderr,
        )
        response: dict[str, bool | str | int | None] = {
            "enabled": None,
            "error": reason,
        }
        with _status_cache_lock:
            _status_inflight = None
            query.set_result(response)
        return dict(response)

    with _status_cache_lock:
        if query_generation == _status_generation:
            _status_cache = (time.monotonic() + STATUS_CACHE_SECONDS, result)
        _status_inflight = None
        query.set_result(result)
    return dict(result)


@router.get("/autostart")
def read_autostart(
    request: Request,
) -> dict[str, bool | str | int | None]:
    if not _is_loopback(request):
        raise HTTPException(status_code=403, detail="Local requests only")
    return get_autostart_status()


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

    def execute_change() -> None:
        try:
            run_task_script(script_name)
        finally:
            invalidate_autostart_status_cache()

    approval = approval_manager.request(
        action=action,
        description=description,
        execute=execute_change,
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
