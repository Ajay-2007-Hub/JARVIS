"""Local auto-start settings endpoints."""

import ipaddress
import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIRECTORY = PROJECT_ROOT / "scripts"
logger = logging.getLogger("jarvis.settings")
router = APIRouter(prefix="/api/settings", tags=["settings"])


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


@router.post("/autostart", status_code=503)
def request_autostart_change(request: Request) -> None:
    if not _is_loopback(request):
        raise HTTPException(status_code=403, detail="Local requests only")
    raise HTTPException(
        status_code=503,
        detail="Auto-start changes are unavailable until approval is enabled",
    )
