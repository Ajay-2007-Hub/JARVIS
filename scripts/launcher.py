"""Start and supervise the local JARVIS backend on Windows."""

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

import psutil
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIRECTORY = Path(
    os.getenv("JARVIS_LOG_DIRECTORY", str(PROJECT_ROOT / "logs"))
)
LOG_DIRECTORY.mkdir(exist_ok=True)
load_dotenv(PROJECT_ROOT / ".env")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5")
BACKEND_URL = "http://127.0.0.1:8000"
MAX_RESTARTS = 3
RESTART_DELAY_SECONDS = 10
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

logger = logging.getLogger("jarvis.launcher")
logger.setLevel(logging.INFO)
if not any(
    isinstance(handler, RotatingFileHandler)
    and Path(handler.baseFilename) == (LOG_DIRECTORY / "jarvis.log").resolve()
    for handler in logger.handlers
):
    log_handler = RotatingFileHandler(
        LOG_DIRECTORY / "jarvis.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    log_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(log_handler)


def is_backend_running() -> bool:
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


def is_ollama_running() -> bool:
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


def wait_until(check: Callable[[], bool], timeout: float, interval: float = 1) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(interval)
    return check()


def find_ollama() -> str | None:
    ollama_path = shutil.which("ollama")
    if ollama_path:
        return ollama_path
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def ensure_ollama() -> bool:
    if is_ollama_running():
        logger.info("Ollama is already running")
        return True

    ollama_executable = find_ollama()
    if not ollama_executable:
        logger.error("Ollama is not running and ollama.exe was not found")
        return False

    logger.info("Starting Ollama service")
    try:
        subprocess.Popen(
            [ollama_executable, "serve"],
            cwd=PROJECT_ROOT,
            creationflags=CREATE_NO_WINDOW,
        )
    except OSError:
        logger.exception("Could not start Ollama")
        return False

    if wait_until(is_ollama_running, timeout=60):
        logger.info("Ollama service is ready")
        return True
    logger.error("Ollama did not become ready within 60 seconds")
    return False


def should_skip_warmup(battery: object | None = None) -> bool:
    battery_status = battery if battery is not None else psutil.sensors_battery()
    return bool(
        battery_status
        and battery_status.percent < 20
        and not battery_status.power_plugged
    )


def warm_model() -> None:
    if should_skip_warmup():
        logger.info("Skipping model warm-up: battery is below 20%% and unplugged")
        return
    logger.info("Warming Ollama model %s", OLLAMA_MODEL)
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": "", "keep_alive": "30m"},
        timeout=300,
    )
    response.raise_for_status()
    logger.info("Model warm-up completed")


def backend_command() -> list[str]:
    pythonw = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    python_executable = pythonw if pythonw.is_file() else Path(sys.executable)
    return [
        str(python_executable),
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--no-use-colors",
    ]


def start_backend() -> subprocess.Popen[bytes]:
    logger.info("Starting JARVIS backend")
    backend_log_path = LOG_DIRECTORY / "backend.log"
    with backend_log_path.open("a", encoding="utf-8") as backend_log:
        return subprocess.Popen(
            backend_command(),
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=backend_log,
            stderr=backend_log,
            creationflags=CREATE_NO_WINDOW,
        )


def wait_for_backend(process: subprocess.Popen[bytes], timeout: float = 90) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_backend_running():
            logger.info("JARVIS backend is healthy")
            return True
        exit_code = process.poll()
        if exit_code is not None:
            logger.error(
                "JARVIS backend exited before becoming healthy with status %s",
                exit_code,
            )
            backend_log = LOG_DIRECTORY / "backend.log"
            try:
                with backend_log.open("r", encoding="utf-8", errors="replace") as log:
                    log_tail = list(deque(log, maxlen=20))
            except OSError:
                logger.exception("Could not read backend log %s", backend_log)
            else:
                logger.error(
                    "Last %s lines of %s:\n%s",
                    len(log_tail),
                    backend_log,
                    "".join(log_tail).rstrip("\n") if log_tail else "(empty)",
                )
            return False
        time.sleep(1)
    logger.error("JARVIS backend did not become healthy within 90 seconds")
    return False


def open_jarvis() -> None:
    logger.info("Opening JARVIS window")
    edge = shutil.which("msedge")
    if edge:
        try:
            subprocess.Popen(
                [edge, f"--app={BACKEND_URL}"],
                cwd=PROJECT_ROOT,
                creationflags=CREATE_NO_WINDOW,
            )
            return
        except OSError:
            logger.exception("Could not launch Edge; using the default browser")
    webbrowser.open(BACKEND_URL)


def show_failure_toast() -> None:
    logger.error("JARVIS failed after %s restarts", MAX_RESTARTS)
    try:
        from plyer import notification

        notification.notify(
            title="JARVIS",
            message="JARVIS failed to start. See logs\\jarvis.log",
            app_name="JARVIS",
        )
    except Exception:
        logger.exception("Could not show Windows notification")


def stop_backend(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def should_restart(restarts_used: int) -> bool:
    return restarts_used < MAX_RESTARTS


def run() -> int:
    if is_backend_running():
        logger.info("JARVIS backend already responds; opening existing instance")
        open_jarvis()
        return 0

    if not ensure_ollama():
        return 1

    try:
        warm_model()
    except requests.RequestException:
        logger.exception("Could not warm the Ollama model")
        return 1

    restarts_used = 0
    tray_started = False
    while True:
        process = start_backend()
        if not wait_for_backend(process):
            stop_backend(process)
        else:
            if not tray_started:
                from backend.tray import run_tray

                threading.Thread(
                    target=run_tray,
                    name="jarvis-tray",
                    daemon=True,
                ).start()
                tray_started = True
                open_jarvis()
            process.wait()
            logger.warning("JARVIS backend exited with status %s", process.returncode)

        if not should_restart(restarts_used):
            show_failure_toast()
            return 1

        restarts_used += 1
        logger.warning(
            "Restarting JARVIS backend (%s/%s) in %s seconds",
            restarts_used,
            MAX_RESTARTS,
            RESTART_DELAY_SECONDS,
        )
        time.sleep(RESTART_DELAY_SECONDS)


if __name__ == "__main__":
    raise SystemExit(run())
