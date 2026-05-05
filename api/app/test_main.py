from fastapi.testclient import TestClient
from httpx import Response

from .main import app

client: TestClient = TestClient(app)


def test_health_check() -> None:
    response: Response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
