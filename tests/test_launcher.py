import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from scripts import launcher


@patch("scripts.launcher.requests.get")
def test_detects_already_running_backend(mock_get: Mock) -> None:
    mock_get.return_value.status_code = 200

    assert launcher.is_backend_running()

    mock_get.assert_called_once_with("http://127.0.0.1:8000/health", timeout=2)


@patch("scripts.launcher.requests.get")
@patch("scripts.launcher.subprocess.Popen")
@patch("scripts.launcher.find_ollama", return_value="C:/Ollama/ollama.exe")
@patch("scripts.launcher.wait_until", return_value=True)
def test_starts_ollama_when_service_is_down(
    mock_wait: Mock,
    mock_find: Mock,
    mock_popen: Mock,
    mock_get: Mock,
) -> None:
    mock_get.side_effect = [
        requests.exceptions.ConnectionError("offline"),
        Mock(status_code=200),
    ]

    assert launcher.ensure_ollama()

    mock_popen.assert_called_once_with(
        ["C:/Ollama/ollama.exe", "serve"],
        cwd=launcher.PROJECT_ROOT,
        creationflags=launcher.CREATE_NO_WINDOW,
    )
    mock_wait.assert_called_once()


def test_skips_warmup_on_low_unplugged_battery() -> None:
    battery = Mock(percent=19, power_plugged=False)

    assert launcher.should_skip_warmup(battery)


def test_does_not_skip_warmup_when_plugged_in() -> None:
    battery = Mock(percent=10, power_plugged=True)

    assert not launcher.should_skip_warmup(battery)


def test_restart_limit_allows_three_restarts_only() -> None:
    assert launcher.should_restart(0)
    assert launcher.should_restart(2)
    assert not launcher.should_restart(3)


@patch("scripts.launcher.subprocess.Popen")
def test_start_backend_redirects_output_and_disables_console(
    mock_popen: Mock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(launcher, "LOG_DIRECTORY", tmp_path)

    launcher.start_backend()

    kwargs = mock_popen.call_args.kwargs
    backend_log = kwargs["stdout"]
    assert kwargs["stderr"] is backend_log
    assert backend_log.name == str(tmp_path / "backend.log")
    assert backend_log.mode == "a"
    assert backend_log.encoding == "utf-8"
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["creationflags"] == launcher.CREATE_NO_WINDOW
    assert "--no-use-colors" in mock_popen.call_args.args[0]
    assert backend_log.closed


def test_early_backend_exit_logs_status_and_last_twenty_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(launcher, "LOG_DIRECTORY", tmp_path)
    (tmp_path / "backend.log").write_text(
        "\n".join(f"line {index}" for index in range(25)),
        encoding="utf-8",
    )
    process = Mock()
    process.poll.return_value = 23

    with caplog.at_level(logging.ERROR, logger="jarvis.launcher"):
        assert not launcher.wait_for_backend(process, timeout=1)

    assert "status 23" in caplog.text
    assert "line 4" not in caplog.text
    assert "line 5" in caplog.text
    assert "line 24" in caplog.text


def test_backend_replaces_missing_standard_streams_in_fresh_process() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; sys.stdout = None; sys.stderr = None; "
                "import backend.main; "
                "assert sys.stdout is not None and sys.stderr is not None"
            ),
        ],
        cwd=launcher.PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
