import logging
import os
import subprocess
import sys
import threading
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

    args, kwargs = mock_popen.call_args
    assert args[0] == ["C:/Ollama/ollama.exe", "serve"]
    assert kwargs["cwd"] == launcher.PROJECT_ROOT
    assert kwargs["creationflags"] == launcher.CREATE_NO_WINDOW
    assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert kwargs["startupinfo"].wShowWindow == subprocess.SW_HIDE
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
    assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert kwargs["startupinfo"].wShowWindow == subprocess.SW_HIDE
    assert kwargs["cwd"] == launcher.PROJECT_ROOT
    assert kwargs["env"]["PYTHONPATH"] == str(launcher.PROJECT_ROOT)
    assert "--no-use-colors" in mock_popen.call_args.args[0]
    assert backend_log.closed


@patch("scripts.launcher.is_backend_running", return_value=False)
def test_early_backend_exit_logs_status_and_last_twenty_lines(
    mock_is_running: Mock,
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
    mock_is_running.assert_called_once_with()


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


def test_launcher_script_imports_tray_from_unrelated_working_directory(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            str(launcher.PROJECT_ROOT / "scripts" / "launcher.py"),
            "--check-imports",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_find_browser_uses_configured_then_installed_then_path_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program_files_x86 = tmp_path / "ProgramFiles86"
    program_files = tmp_path / "ProgramFiles"
    local_app_data = tmp_path / "LocalAppData"
    configured = tmp_path / "configured-browser.exe"
    expected_paths = [
        configured,
        program_files_x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        program_files / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        local_app_data / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        program_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        program_files / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    monkeypatch.setenv("BROWSER_PATH", str(configured))
    monkeypatch.setenv("ProgramFiles(x86)", str(program_files_x86))
    monkeypatch.setenv("ProgramFiles", str(program_files))
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    for candidate in expected_paths:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.touch()

    for candidate in expected_paths:
        assert launcher.find_browser() == str(candidate)
        candidate.unlink()

    mock_which = Mock(side_effect=[None, None, "C:/Chrome/chrome.exe"])
    monkeypatch.setattr(launcher.shutil, "which", mock_which)
    assert launcher.find_browser() == "C:/Chrome/chrome.exe"
    assert [call.args[0] for call in mock_which.call_args_list] == [
        "msedge",
        "brave",
        "chrome",
    ]


@patch("scripts.launcher.find_browser", return_value=None)
@patch("scripts.launcher.webbrowser.open", return_value=True)
def test_open_jarvis_falls_back_when_no_browser_is_found(
    mock_open: Mock, mock_find_browser: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    launcher.open_jarvis()

    mock_find_browser.assert_called_once_with()
    mock_open.assert_called_once_with(launcher.BACKEND_URL)
    assert "Opening UI via default browser" in caplog.text
    assert "UI opened" in caplog.text


def test_open_jarvis_launches_selected_browser_in_app_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser_path = "C:/Program Files/Brave/brave.exe"
    mock_popen = Mock()
    monkeypatch.setattr(launcher, "find_browser", Mock(return_value=browser_path))
    monkeypatch.setattr(launcher.subprocess, "Popen", mock_popen)

    launcher.open_jarvis()

    mock_popen.assert_called_once_with(
        [browser_path, "--app=http://127.0.0.1:8000"],
        cwd=launcher.PROJECT_ROOT,
        creationflags=launcher.CREATE_NO_WINDOW,
    )


@patch("backend.tray.run_tray", side_effect=RuntimeError("tray failed"))
def test_tray_failure_is_logged_without_escaping(
    mock_run_tray: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    launcher._run_tray()

    mock_run_tray.assert_called_once_with()
    assert "System tray failed" in caplog.text
    assert "RuntimeError: tray failed" in caplog.text


def test_open_ui_failure_does_not_stop_supervision(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(launcher, "clear_shutdown_request", Mock())
    monkeypatch.setattr(launcher, "is_backend_running", Mock(return_value=True))
    monkeypatch.setattr(launcher, "find_browser", Mock(return_value=None))
    monkeypatch.setattr(
        launcher, "webbrowser", Mock(open=Mock(side_effect=OSError("browser failed")))
    )
    monkeypatch.setattr(launcher, "start_tray", Mock())
    supervise = Mock(return_value=0)
    monkeypatch.setattr(launcher, "supervise_existing_backend", supervise)

    assert launcher.run() == 0

    assert "Could not open UI via the default browser" in caplog.text
    supervise.assert_called_once_with()


def test_main_logs_unhandled_exception(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    monkeypatch.setattr(
        launcher, "run", Mock(side_effect=RuntimeError("unexpected failure"))
    )

    assert launcher.main() == 1

    assert "JARVIS launcher failed" in caplog.text
    assert "RuntimeError: unexpected failure" in caplog.text
    assert sys.excepthook is launcher._log_uncaught_exception
    assert threading.excepthook is launcher._log_thread_exception


def test_already_running_backend_is_supervised_until_shutdown(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(launcher, "clear_shutdown_request", Mock())
    monkeypatch.setattr(launcher, "is_backend_running", Mock(return_value=True))
    monkeypatch.setattr(
        launcher, "shutdown_requested", Mock(side_effect=[False, False, True])
    )
    monkeypatch.setattr(launcher.time, "sleep", Mock())
    monkeypatch.setattr(launcher, "open_jarvis", Mock())
    monkeypatch.setattr(launcher, "start_tray", Mock())
    start_backend = Mock()
    monkeypatch.setattr(launcher, "start_backend", start_backend)

    assert launcher.run() == 0

    launcher.open_jarvis.assert_called_once_with()
    launcher.start_tray.assert_called_once_with()
    start_backend.assert_not_called()
    assert "Supervising backend" in caplog.text
