import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from subprocess import CompletedProcess
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import pytest

from backend import settings
from backend.main import app
from backend.security.approval import ApprovalManager

client = TestClient(app, client=("127.0.0.1", 50000))


def status_json(
    enabled: bool = True,
    registered: bool = True,
    state: str = "Ready",
    last_result: int = 0,
) -> str:
    return json.dumps(
        {
            "registered": registered,
            "enabled": enabled,
            "state": state,
            "last_result": last_result,
        }
    )


def scheduler_status(registered: bool, enabled: bool) -> dict[str, bool | str | int]:
    return {
        "enabled": enabled,
        "registered": registered,
        "state": "Ready" if enabled else "Disabled",
        "last_result": 0,
    }


@pytest.fixture(autouse=True)
def reset_approval_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "approval_manager", ApprovalManager())
    settings.invalidate_autostart_status_cache()


@patch("backend.settings.subprocess.run")
def test_status_query_reports_enabled(mock_run: Mock) -> None:
    mock_run.return_value = CompletedProcess(
        args=[],
        returncode=0,
        stdout=status_json(enabled=True, state="Ready", last_result=0),
        stderr="",
    )

    response = client.get("/api/settings/autostart")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "registered": True,
        "state": "Ready",
        "last_result": 0,
    }
    args, kwargs = mock_run.call_args
    command = args[0]
    assert command[0] == "powershell.exe"
    assert command[1:8] == [
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-Command",
    ]
    assert kwargs["cwd"] == settings.PROJECT_ROOT
    assert kwargs["timeout"] == 10
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["creationflags"] == settings.CREATE_NO_WINDOW
    assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert kwargs["startupinfo"].wShowWindow == subprocess.SW_HIDE
    assert kwargs["shell"] is False
    assert "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8" in command[-1]
    assert "Get-ScheduledTaskInfo -TaskName JARVIS" in command[-1]


@patch("backend.settings.subprocess.run")
def test_status_query_reports_disabled(mock_run: Mock) -> None:
    mock_run.return_value = CompletedProcess(
        args=[],
        returncode=0,
        stdout=status_json(enabled=False, state="Disabled", last_result=1),
        stderr="",
    )

    response = client.get("/api/settings/autostart")

    assert response.json() == {
        "enabled": False,
        "registered": True,
        "state": "Disabled",
        "last_result": 1,
    }


@patch("backend.settings.subprocess.run")
def test_not_registered_task_reports_disabled(mock_run: Mock) -> None:
    mock_run.return_value = CompletedProcess(
        args=[],
        returncode=0,
        stdout='{"registered":false,"enabled":false}',
        stderr="",
    )

    response = client.get("/api/settings/autostart")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "registered": False,
        "state": "Not registered",
        "last_result": 0,
    }


@patch("backend.settings.subprocess.run")
def test_malformed_status_json_returns_error_and_logs_output(
    mock_run: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    mock_run.return_value = CompletedProcess(
        args=[], returncode=0, stdout="{not json", stderr="unexpected output"
    )

    response = client.get("/api/settings/autostart")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": None,
        "error": "Invalid Task Scheduler status response",
    }
    assert "{not json" in caplog.text
    assert "unexpected output" in caplog.text
    assert "Traceback (most recent call last)" in caplog.text


@patch("backend.settings.subprocess.run")
def test_status_query_timeout_returns_error_and_logs_output(
    mock_run: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    mock_run.side_effect = subprocess.TimeoutExpired(
        cmd="powershell.exe", timeout=10, output="partial output", stderr="timed out"
    )

    response = client.get("/api/settings/autostart")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": None,
        "error": "Task Scheduler status query timed out",
    }
    assert "partial output" in caplog.text
    assert "timed out" in caplog.text


@patch("backend.settings.subprocess.run")
def test_status_query_accepts_utf8_bom(mock_run: Mock) -> None:
    mock_run.return_value = CompletedProcess(
        args=[],
        returncode=0,
        stdout="\ufeff" + status_json(enabled=True, state="Ready", last_result=2),
        stderr="",
    )

    response = client.get("/api/settings/autostart")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "registered": True,
        "state": "Ready",
        "last_result": 2,
    }


@patch("backend.settings.subprocess.run")
def test_status_is_cached(mock_run: Mock) -> None:
    mock_run.return_value = CompletedProcess(
        args=[],
        returncode=0,
        stdout=status_json(enabled=True),
        stderr="",
    )

    expected = {
        "enabled": True,
        "registered": True,
        "state": "Ready",
        "last_result": 0,
    }
    assert client.get("/api/settings/autostart").json() == expected
    assert client.get("/api/settings/autostart").json() == expected

    mock_run.assert_called_once()


@patch("backend.settings.subprocess.run")
def test_status_cache_expires_after_thirty_seconds(
    mock_run: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_run.return_value = CompletedProcess(
        args=[],
        returncode=0,
        stdout=status_json(enabled=True),
        stderr="",
    )
    clock = Mock(side_effect=[10.0, 11.0, 12.0, 42.0, 43.0])
    monkeypatch.setattr(settings.time, "monotonic", clock)

    assert settings.get_autostart_status()["enabled"] is True
    assert settings.get_autostart_status()["enabled"] is True
    assert settings.get_autostart_status()["enabled"] is True

    assert mock_run.call_count == 2


@patch("backend.settings.subprocess.run")
def test_concurrent_status_requests_share_one_query(mock_run: Mock) -> None:
    query_started = threading.Event()
    release_query = threading.Event()

    def run_query(*args, **kwargs) -> CompletedProcess[str]:
        query_started.set()
        if not release_query.wait(timeout=5):
            raise TimeoutError("test query was not released")
        return CompletedProcess(
            args=[], returncode=0, stdout=status_json(enabled=True), stderr=""
        )

    mock_run.side_effect = run_query
    barrier = threading.Barrier(6)

    def request_status() -> dict[str, bool | str | int | None]:
        barrier.wait()
        return settings.get_autostart_status()

    with ThreadPoolExecutor(max_workers=5) as executor:
        requests = [executor.submit(request_status) for _ in range(5)]
        barrier.wait()
        assert query_started.wait(timeout=5)
        release_query.set()
        responses = [request.result() for request in requests]

    assert all(
        response["enabled"] is True and response["registered"] is True
        for response in responses
    )
    mock_run.assert_called_once()


@pytest.mark.parametrize(
    ("enabled", "initial_status", "updated_status", "script_name"),
    [
        (True, "Disabled", "Ready", "register_autostart.ps1"),
        (False, "Ready", "Disabled", "unregister_autostart.ps1"),
    ],
)
def test_approved_change_invalidates_status_cache(
    enabled: bool,
    initial_status: str,
    updated_status: str,
    script_name: str,
) -> None:
    with (
        patch("backend.settings._query_autostart_status") as mock_query,
        patch("backend.settings.run_powershell_command") as mock_command,
        patch("backend.settings.run_task_script") as mock_script,
    ):
        mock_query.side_effect = [
            scheduler_status(True, initial_status != "Disabled"),
            scheduler_status(True, initial_status != "Disabled"),
            scheduler_status(True, updated_status != "Disabled"),
        ]
        assert client.get("/api/settings/autostart").json()["enabled"] is (
            initial_status != "Disabled"
        )
        request = client.post(
            "/api/settings/autostart", json={"enabled": enabled}
        )
        approval_id = request.json()["approval"]["id"]
        response = client.post(f"/api/approvals/{approval_id}/approve")
        assert response.status_code == 200
        assert client.get("/api/settings/autostart").json()["enabled"] is (
            updated_status != "Disabled"
        )

    expected_command = (
        "Enable-ScheduledTask -TaskName JARVIS -ErrorAction Stop | Out-Null"
        if enabled
        else "Disable-ScheduledTask -TaskName JARVIS -ErrorAction Stop | Out-Null"
    )
    mock_command.assert_called_once_with(expected_command)
    mock_script.assert_not_called()
    assert mock_query.call_count == 3


@patch("backend.settings.subprocess.run")
def test_powershell_scripts_run_hidden_without_a_shell(mock_run: Mock) -> None:
    mock_run.return_value = CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    settings.run_task_script("register_autostart.ps1")

    args, kwargs = mock_run.call_args
    assert args[0] == [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(settings.SCRIPTS_DIRECTORY / "register_autostart.ps1"),
    ]
    assert kwargs["creationflags"] == settings.CREATE_NO_WINDOW
    assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert kwargs["startupinfo"].wShowWindow == subprocess.SW_HIDE
    assert kwargs["shell"] is False


def test_settings_endpoints_reject_non_local_clients() -> None:
    remote_client = TestClient(app, client=("192.0.2.1", 50000))

    get_response = remote_client.get("/api/settings/autostart")
    post_response = remote_client.post(
        "/api/settings/autostart", json={"enabled": True}
    )

    assert get_response.status_code == 403
    assert post_response.status_code == 403


def test_post_creates_approval_without_changing_system() -> None:
    with patch("backend.settings.run_task_script") as mock_script:
        response = client.post(
            "/api/settings/autostart", json={"enabled": True}
        )

    assert response.status_code == 202
    approval = response.json()["approval"]
    assert approval["action"] == "enable_autostart"
    assert approval["status"] == "pending"
    mock_script.assert_not_called()


@patch(
    "backend.settings._query_autostart_status",
    return_value=scheduler_status(False, False),
)
@patch("backend.settings.run_task_script")
def test_approved_enable_registers_missing_task(
    mock_script: Mock, mock_query: Mock
) -> None:
    request_response = client.post(
        "/api/settings/autostart", json={"enabled": True}
    )
    approval_id = request_response.json()["approval"]["id"]

    approval_response = client.post(f"/api/approvals/{approval_id}/approve")

    assert approval_response.status_code == 200
    assert approval_response.json()["approval"]["status"] == "approved"
    mock_script.assert_called_once_with("register_autostart.ps1")
    mock_query.assert_called_once_with()


@pytest.mark.parametrize(
    ("current_enabled", "requested_enabled"),
    [(True, True), (False, False)],
)
def test_already_desired_task_state_is_no_op(
    current_enabled: bool, requested_enabled: bool
) -> None:
    with (
        patch(
            "backend.settings._query_autostart_status",
            return_value=scheduler_status(True, current_enabled),
        ) as mock_query,
        patch("backend.settings.run_powershell_command") as mock_command,
        patch("backend.settings.run_task_script") as mock_script,
    ):
        settings.set_autostart_enabled(requested_enabled)

    mock_query.assert_called_once_with()
    mock_command.assert_not_called()
    mock_script.assert_not_called()


def test_enable_existing_disabled_task_without_re_registering() -> None:
    with (
        patch(
            "backend.settings._query_autostart_status",
            return_value=scheduler_status(True, False),
        ) as mock_query,
        patch("backend.settings.run_powershell_command") as mock_command,
        patch("backend.settings.run_task_script") as mock_script,
    ):
        settings.set_autostart_enabled(True)

    mock_query.assert_called_once_with()
    mock_command.assert_called_once_with(
        "Enable-ScheduledTask -TaskName JARVIS -ErrorAction Stop | Out-Null"
    )
    mock_script.assert_not_called()


def test_disable_enabled_task_without_unregistering() -> None:
    with (
        patch(
            "backend.settings._query_autostart_status",
            return_value=scheduler_status(True, True),
        ) as mock_query,
        patch("backend.settings.run_powershell_command") as mock_command,
        patch("backend.settings.run_task_script") as mock_script,
    ):
        settings.set_autostart_enabled(False)

    mock_query.assert_called_once_with()
    mock_command.assert_called_once_with(
        "Disable-ScheduledTask -TaskName JARVIS -ErrorAction Stop | Out-Null"
    )
    mock_script.assert_not_called()


def test_disable_missing_task_is_no_op() -> None:
    with (
        patch(
            "backend.settings._query_autostart_status",
            return_value=scheduler_status(False, False),
        ) as mock_query,
        patch("backend.settings.run_powershell_command") as mock_command,
        patch("backend.settings.run_task_script") as mock_script,
    ):
        settings.set_autostart_enabled(False)

    mock_query.assert_called_once_with()
    mock_command.assert_not_called()
    mock_script.assert_not_called()


@patch("backend.settings.subprocess.run")
def test_scheduled_task_enable_command_runs_hidden_without_shell(
    mock_run: Mock,
) -> None:
    mock_run.return_value = CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    settings.run_powershell_command(
        "Enable-ScheduledTask -TaskName JARVIS -ErrorAction Stop | Out-Null"
    )

    args, kwargs = mock_run.call_args
    assert args[0][:8] == [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-Command",
    ]
    assert args[0][-1].startswith("Enable-ScheduledTask")
    assert kwargs["creationflags"] == settings.CREATE_NO_WINDOW
    assert kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert kwargs["startupinfo"].wShowWindow == subprocess.SW_HIDE
    assert kwargs["shell"] is False


@patch("backend.settings.run_task_script")
def test_denied_settings_change_does_not_run_script(mock_script: Mock) -> None:
    request_response = client.post(
        "/api/settings/autostart", json={"enabled": False}
    )
    approval_id = request_response.json()["approval"]["id"]

    approval_response = client.post(f"/api/approvals/{approval_id}/deny")

    assert approval_response.status_code == 200
    assert approval_response.json()["approval"]["status"] == "denied"
    mock_script.assert_not_called()


def test_approval_is_rejected_after_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "approval_manager", ApprovalManager(expiry_seconds=0)
    )
    request_response = client.post(
        "/api/settings/autostart", json={"enabled": True}
    )
    approval_id = request_response.json()["approval"]["id"]

    response = client.post(f"/api/approvals/{approval_id}/approve")

    assert response.status_code == 410


def test_pending_approvals_endpoint_is_local_only() -> None:
    remote_client = TestClient(app, client=("192.0.2.1", 50000))

    response = remote_client.get("/api/approvals")

    assert response.status_code == 403


def test_task_script_command_is_allowlisted() -> None:
    try:
        settings.run_task_script("unexpected.ps1")
    except ValueError as error:
        assert str(error) == "Unsupported scheduled-task script"
    else:
        raise AssertionError("Unexpected script name should be rejected")
