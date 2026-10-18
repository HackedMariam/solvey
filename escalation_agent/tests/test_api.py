"""
Integration tests for FastAPI endpoints (/health, /escalate, /format-preview).
"""

from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_health_check_endpoint():
    """Verify /health returns status and mode info."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "ticketing_mode" in data
    assert "is_mock_mode" in data


def test_escalate_endpoint_mock_success():
    """Verify /escalate endpoint returns structured success in mock mode."""
    payload = {
        "case_id": "CASE-API-1",
        "user_request": "Docker container fails to start because port 8080 is allocated.",
        "triage": {"category": "Docker", "urgency": "high"},
        "escalation": {
            "required": True,
            "reason": "Troubleshooting failed to free port.",
        },
    }
    response = client.post("/escalate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["mode"] == "mock"
    assert data["escalated"] is True
    assert data["ticket"]["id"] == "MOCK-API-1"
    assert data["ticket"]["priority"] == "High"


def test_escalate_endpoint_skipped_not_required():
    """Verify /escalate endpoint returns skipped status when escalation is false."""
    payload = {
        "case_id": "CASE-API-2",
        "user_request": "How do I request access to GitHub repo?",
        "escalation": {
            "required": False,
            "reason": "Automated self-service form link provided.",
        },
    }
    response = client.post("/escalate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "skipped"
    assert data["escalated"] is False
    assert data["reason"] == "escalation_not_required"


def test_escalate_endpoint_missing_escalation_error():
    """Verify /escalate endpoint returns structured error when escalation is omitted."""
    payload = {
        "case_id": "CASE-API-3",
        "user_request": "Database connection timeout.",
    }
    response = client.post("/escalate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert data["escalated"] is False
    assert "Missing escalation decision" in data["error"]


def test_format_preview_endpoint():
    """Verify /format-preview generates Jira payload without submitting."""
    payload = {
        "case_id": "CASE-API-4",
        "user_request": "Kubernetes Ingress certificate expired.",
        "triage": {"category": "Kubernetes", "urgency": "critical"},
        "escalation": {
            "required": True,
            "reason": "SSL cert renewal failed.",
        },
    }
    response = client.post("/format-preview", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "synthesized_ticket" in data
    assert "jira_payload" in data
    assert data["jira_payload"]["fields"]["priority"]["name"] == "Highest"
