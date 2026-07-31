from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import create_app


@pytest.fixture
def mock_diagnosis_service():
    service = MagicMock()
    service.submit.return_value = "batch_test123456"
    return service


@pytest.fixture
def client(mock_diagnosis_service):
    app = create_app(diagnosis_service=mock_diagnosis_service)
    with TestClient(app) as test_client:
        yield test_client


class TestHealth:

    def test_health_returns_ok(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestDiagnose:

    def test_accepts_and_enqueues(
        self, client, mock_diagnosis_service
    ):
        payload = {
            "batch": [{"faultNumber": 7, "xmeas_1": 1.0}],
            "meta": {"batch_id": "batch_test123456"},
        }

        response = client.post("/diagnose", json=payload)

        assert response.status_code == 202
        body = response.json()
        assert body == {
            "accepted": True,
            "batch_id": "batch_test123456",
        }
        mock_diagnosis_service.submit.assert_called_once_with(payload)

    def test_rejects_empty_batch(
        self, client, mock_diagnosis_service
    ):
        response = client.post(
            "/diagnose",
            json={"batch": [], "meta": {}},
        )

        assert response.status_code == 400
        mock_diagnosis_service.submit.assert_not_called()

    def test_rejects_missing_batch(
        self, client, mock_diagnosis_service
    ):
        response = client.post(
            "/diagnose",
            json={"meta": {}},
        )

        assert response.status_code == 422
        mock_diagnosis_service.submit.assert_not_called()


class TestLifecycle:

    def test_start_called_on_startup(self, mock_diagnosis_service):
        app = create_app(diagnosis_service=mock_diagnosis_service)

        with TestClient(app):
            mock_diagnosis_service.start.assert_called_once()

        mock_diagnosis_service.stop.assert_called_once()
