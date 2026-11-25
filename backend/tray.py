"""Windows system-tray controls for the local JARVIS application."""

import logging
import shutil
import subprocess
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pystray
import requests
from PIL import Image, ImageDraw
from pystray import Menu, MenuItem

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIRECTORY = PROJECT_ROOT / "logs"
LOG_DIRECTORY.mkdir(exist_ok=True)
BACKEND_URL = "http://127.0.0.1:8000"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

logger = logging.getLogger("jarvis.tray")
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

_listening_paused = False


def open_jarvis(icon: pystray.Icon, item: MenuItem) -> None:
    del icon, item
    edge = shutil.which("msedge")
    if edge:
        try:
            subprocess.Popen(
                [edge, f"--app={BACKEND_URL}"],
                cwd=PROJECT_ROOT,
                creationflags=CREATE_NO_WINDOW,
            )
            logger.info("Opened JARVIS in Edge app mode")
            return
        except OSError:
            logger.exception("Could not launch Edge; using the default browser")
    webbrowser.open(BACKEND_URL)
    logger.info("Opened JARVIS in the default browser")


def toggle_listening(icon: pystray.Icon, item: MenuItem) -> None:
    del icon, item
    global _listening_paused
    try:
        response = requests.post(f"{BACKEND_URL}/api/listening", timeout=2)
        response.raise_for_status()
        _listening_paused = not response.json()["listening"]
        logger.info("Listening paused: %s", _listening_paused)
    except (requests.RequestException, KeyError, ValueError):
        logger.exception("Could not toggle listening state")


def quit_jarvis(icon: pystray.Icon, item: MenuItem) -> None:
    del item
    try:
        response = requests.post(f"{BACKEND_URL}/api/shutdown", timeout=2)
        response.raise_for_status()
        logger.info("Requested JARVIS shutdown from tray")
    except requests.RequestException:
        logger.exception("Could not request JARVIS shutdown")
    finally:
        icon.stop()


def create_icon_image() -> Image.Image:
    image = Image.new("RGB", (64, 64), "#10182a")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill="#45c6da")
    draw.text((21, 14), "J", fill="#07121d", stroke_width=1)
    return image


def run_tray() -> None:
    menu = Menu(
        MenuItem("Open JARVIS", open_jarvis, default=True),
        MenuItem(
            lambda item: (
                "Resume listening" if _listening_paused else "Pause listening"
            ),
            toggle_listening,
        ),
        MenuItem("Quit", quit_jarvis),
    )
    icon = pystray.Icon(
        "JARVIS",
        create_icon_image(),
        "JARVIS",
        menu,
    )
    logger.info("Starting JARVIS system tray icon")
    icon.run()
