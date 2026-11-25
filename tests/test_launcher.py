from unittest.mock import Mock, patch

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
