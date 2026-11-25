from subprocess import CompletedProcess
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend import settings
from backend.main import app

client = TestClient(app, client=("127.0.0.1", 50000))


@patch("backend.settings.subprocess.run")
def test_status_script_reports_enabled(mock_run: Mock) -> None:
    mock_run.return_value = CompletedProcess(
        args=[], returncode=0, stdout="enabled=true\nlast_run_result=0\n", stderr=""
    )

    response = client.get("/api/settings/autostart")

    assert response.status_code == 200
    assert response.json() == {"enabled": True}
    mock_run.assert_called_once_with(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(settings.SCRIPTS_DIRECTORY / "status_autostart.ps1"),
        ],
        cwd=settings.PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )


@patch("backend.settings.subprocess.run")
def test_status_script_reports_disabled(mock_run: Mock) -> None:
    mock_run.return_value = CompletedProcess(
        args=[], returncode=0, stdout="enabled=false\n", stderr=""
    )

    response = client.get("/api/settings/autostart")

    assert response.json() == {"enabled": False}


@patch("backend.settings.subprocess.run", side_effect=OSError("powershell missing"))
def test_status_script_failure_is_reported(mock_run: Mock) -> None:
    response = client.get("/api/settings/autostart")

    assert response.status_code == 503
    assert response.json()["detail"] == "Could not read auto-start status"


def test_settings_endpoints_reject_non_local_clients() -> None:
    remote_client = TestClient(app, client=("192.0.2.1", 50000))

    get_response = remote_client.get("/api/settings/autostart")
    post_response = remote_client.post(
        "/api/settings/autostart", json={"enabled": True}
    )

    assert get_response.status_code == 403
    assert post_response.status_code == 403


def test_post_does_not_change_system_before_approval() -> None:
    with patch("backend.settings.run_task_script") as mock_script:
        response = client.post(
            "/api/settings/autostart", json={"enabled": True}
        )

    assert response.status_code == 503
    mock_script.assert_not_called()


def test_task_script_command_is_allowlisted() -> None:
    try:
        settings.run_task_script("unexpected.ps1")
    except ValueError as error:
        assert str(error) == "Unsupported scheduled-task script"
    else:
        raise AssertionError("Unexpected script name should be rejected")
