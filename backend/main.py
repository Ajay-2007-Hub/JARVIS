"""Local API for the JARVIS project."""

import ipaddress
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import requests
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles

from backend.settings import approvals_router, router as settings_router

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIRECTORY = Path(
    os.getenv("JARVIS_LOG_DIRECTORY", str(PROJECT_ROOT / "logs"))
)
LOG_DIRECTORY.mkdir(exist_ok=True)
load_dotenv(PROJECT_ROOT / ".env")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5")

logger = logging.getLogger("jarvis")
logger.setLevel(logging.INFO)
if not any(
    isinstance(handler, RotatingFileHandler)
    and Path(handler.baseFilename) == (LOG_DIRECTORY / "jarvis.log").resolve()
    for handler in logger.handlers
):
    file_handler = RotatingFileHandler(
        LOG_DIRECTORY / "jarvis.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)

app = FastAPI(title="JARVIS")
app.state.listening_enabled = True
app.include_router(settings_router)
app.include_router(approvals_router)


def _is_loopback(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def _signal_shutdown() -> None:
    logger.info("Graceful shutdown requested")
    os.kill(os.getpid(), signal.SIGINT)


@app.get("/health")
def health() -> dict[str, bool | str]:
    """Report API health and whether the configured Ollama model is loaded."""
    ollama_ok = False
    model_loaded = False
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        response.raise_for_status()
        ollama_ok = True
        models = response.json().get("models", [])
        model_loaded = any(
            model_name == OLLAMA_MODEL
            or model_name.partition(":")[0] == OLLAMA_MODEL
            or OLLAMA_MODEL.partition(":")[0] == model_name.partition(":")[0]
            for model in models
            if (model_name := model.get("name") or model.get("model"))
        )
    except (requests.RequestException, ValueError, TypeError) as error:
        logger.info("Ollama health check failed: %s", error)
    return {
        "status": "ok",
        "ollama_ok": ollama_ok,
        "model_loaded": model_loaded,
    }


@app.post("/api/chat")
def chat() -> dict[str, str]:
    """Placeholder chat endpoint; model integration will be added later."""
    return {"reply": "Chat is not implemented yet."}


@app.post("/api/shutdown")
def shutdown(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Request graceful shutdown from a local client."""
    if not _is_loopback(request):
        raise HTTPException(status_code=403, detail="Local requests only")
    background_tasks.add_task(_signal_shutdown)
    return {"status": "shutting_down"}


@app.post("/api/listening")
def toggle_listening(request: Request) -> dict[str, bool]:
    """Toggle the placeholder listening state for the future voice integration."""
    if not _is_loopback(request):
        raise HTTPException(status_code=403, detail="Local requests only")
    app.state.listening_enabled = not app.state.listening_enabled
    logger.info("Listening enabled: %s", app.state.listening_enabled)
    return {"listening": app.state.listening_enabled}


frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
