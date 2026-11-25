from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_reports_api_is_responding() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_endpoint_is_a_placeholder() -> None:
    response = client.post("/api/chat")

    assert response.status_code == 200
    assert response.json() == {"reply": "Chat is not implemented yet."}
