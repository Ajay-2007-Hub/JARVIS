from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import requests

from backend.main import OLLAMA_MODEL, app

client = TestClient(app, client=("127.0.0.1", 50000))


@patch("backend.main.requests.get")
def test_health_reports_ollama_and_model_status(mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = {"models": [{"name": f"{OLLAMA_MODEL}:latest"}]}
    mock_get.return_value = mock_response

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ollama_ok": True,
        "model_loaded": True,
    }
    mock_get.assert_called_once_with(
        "http://127.0.0.1:11434/api/tags", timeout=2
    )


@patch(
    "backend.main.requests.get",
    side_effect=requests.exceptions.ConnectionError("offline"),
)
def test_health_handles_ollama_down(mock_get: Mock) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ollama_ok": False,
        "model_loaded": False,
    }


@patch("backend.main.requests.get")
def test_health_reports_missing_model(mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = {"models": [{"name": "another-model:latest"}]}
    mock_get.return_value = mock_response

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ollama_ok": True,
        "model_loaded": False,
    }


def test_chat_endpoint_is_a_placeholder() -> None:
    response = client.post("/api/chat")

    assert response.status_code == 200
    assert response.json() == {"reply": "Chat is not implemented yet."}


@patch("backend.main._signal_shutdown")
def test_shutdown_schedules_graceful_shutdown(
    mock_shutdown: Mock, tmp_path, monkeypatch
) -> None:
    marker = tmp_path / "shutdown.requested"
    monkeypatch.setattr("backend.main.SHUTDOWN_MARKER", marker)

    response = client.post("/api/shutdown")

    assert response.status_code == 200
    assert response.json() == {"status": "shutting_down"}
    assert marker.read_text(encoding="utf-8") == "shutdown requested\n"
    mock_shutdown.assert_called_once_with()


def test_shutdown_rejects_non_local_client() -> None:
    remote_client = TestClient(app, client=("192.0.2.1", 50000))

    response = remote_client.post("/api/shutdown")

    assert response.status_code == 403


def test_listening_endpoint_toggles_local_state() -> None:
    app.state.listening_enabled = True

    first_response = client.post("/api/listening")
    second_response = client.post("/api/listening")

    assert first_response.json() == {"listening": False}
    assert second_response.json() == {"listening": True}


def test_listening_endpoint_rejects_non_local_client() -> None:
    remote_client = TestClient(app, client=("192.0.2.1", 50000))

    response = remote_client.post("/api/listening")

    assert response.status_code == 403


def test_frontend_is_served_when_built() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "<div id=\"root\"></div>" in response.text
