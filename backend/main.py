"""Minimal local API for the JARVIS project."""

import logging
from pathlib import Path

from fastapi import FastAPI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIRECTORY = PROJECT_ROOT / "logs"
LOG_DIRECTORY.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOG_DIRECTORY / "jarvis.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="JARVIS")


@app.get("/health")
async def health() -> dict[str, str]:
    """Report that the local API is responding."""
    return {"status": "ok"}


@app.post("/api/chat")
async def chat() -> dict[str, str]:
    """Placeholder chat endpoint; model integration will be added later."""
    return {"reply": "Chat is not implemented yet."}
