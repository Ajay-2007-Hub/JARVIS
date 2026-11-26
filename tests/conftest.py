import logging
import os
import shutil
import tempfile
from pathlib import Path


_TEMP_LOG_DIRECTORY = Path(tempfile.mkdtemp(prefix="jarvis-pytest-logs-"))
os.environ["JARVIS_LOG_DIRECTORY"] = str(_TEMP_LOG_DIRECTORY)


def pytest_unconfigure(config: object) -> None:
    for logger_name in ("jarvis", "jarvis.launcher"):
        app_logger = logging.getLogger(logger_name)
        for handler in app_logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                handler.close()
                app_logger.removeHandler(handler)
    shutil.rmtree(_TEMP_LOG_DIRECTORY, ignore_errors=True)
