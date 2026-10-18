"""
Integration-style test suite verifying all 9 required scenarios.
Tests run completely without real external credentials.
"""

from unittest.mock import MagicMock, patch
import pytest

from config import Settings
from workflow import execute_escalation_workflow


# ==============================================================================
# Scenario 1: Unknown Error (RAG returns zero documents, upstream escalates)
# ==============================================================================
def test_scenario_1_unknown_error_zero_rag_documents():
    """
    RAG returns 0 relevant documents; upstream workflow marks case for escalation.
    Component must NOT recalculate escalation; it must preserve and record the escalation reason.
    """
    payload = {
        "case_id": "CASE-SCENARIO-1",
        "user_request": "Internal app crashes with cryptic error code 0x8849.",
        "vision_findings": {
            "observations": ["Screenshot shows crash dialog with code 0x8849"],
            "extracted_text": "Fatal exception 0x8849 in libinternal.dll",
        },
        "triage": {
            "category": "Software",
            "urgency": "medium",
        },
        "rag": {
            "status": "no_documents_found",
            "document_count": 0,
            "sources": [],
            "findings": [],
        },
        "resolution": {
            "status": "failed",
            "attempted_steps": [],
            "user_feedback": None,
        },
        "escalation": {
            "required": True,
            "reason": "No documentation exists for error 0x8849; requires developer investigation.",
        },
    }

    mock_cfg = Settings(TICKETING_MODE="mock", LLM_PROVIDER="mock")
    response = execute_escalation_workflow(payload, config=mock_cfg)

    assert response.status == "success"
    assert response.escalated is True
    assert response.case_id == "CASE-SCENARIO-1"
    assert response.ticket is not None
    assert response.ticket.escalation_reason == "No documentation exists for error 0x8849; requires developer investigation."
    assert "0x8849" in response.ticket.title or "0x8849" in response.ticket.summary
    assert response.ticket.priority == "Medium"


# ==============================================================================
# Scenario 2: Failed Resolution (Troubleshooting steps failed, user reported)
# ==============================================================================
def test_scenario_2_failed_resolution():
    """
    User reports that previous troubleshooting did not work; upstream workflow escalates.
    Component must record attempted steps, feedback, and escalation reason.
    """
    payload = {
        "case_id": "CASE-SCENARIO-2",
        "user_request": "Outlook disconnects every 10 minutes.",
        "triage": {
            "category": "Email",
            "subcategory": "Outlook",
            "urgency": "high",
        },
        "rag": {
            "status": "documents_found",
            "document_count": 1,
            "sources": ["Outlook Troubleshooting Standard SOP"],
            "findings": ["Disable cached exchange mode"],
        },
        "resolution": {
            "status": "failed",
            "attempted_steps": [
                "Recreated Outlook profile",
                "Disabled cached exchange mode",
            ],
            "user_feedback": "Outlook continues to disconnect every 10 minutes even after profile recreation.",
        },
        "escalation": {
            "required": True,
            "reason": "Documented troubleshooting procedures failed to stabilize connection.",
        },
    }

    mock_cfg = Settings(TICKETING_MODE="mock", LLM_PROVIDER="mock")
    response = execute_escalation_workflow(payload, config=mock_cfg)

    assert response.status == "success"
    assert response.escalated is True
    assert response.ticket.priority == "High"
    assert response.ticket.escalation_reason == "Documented troubleshooting procedures failed to stabilize connection."
    # Verify attempted steps and user feedback are tracked
    attempted_str = str(response.ticket.attempted_actions)
    assert "Recreated Outlook profile" in attempted_str
    assert "Outlook continues to disconnect" in attempted_str


# ==============================================================================
# Scenario 3: Critical Incident (Triage marks critical, immediate escalation)
# ==============================================================================
def test_scenario_3_critical_incident():
    """
    Triage marks the case as critical; upstream requests immediate escalation.
    Component preserves urgency (maps to Highest) and records escalation without recalculation.
    """
    payload = {
        "case_id": "CASE-SCENARIO-3",
        "user_request": "Production payment processing gateway is returning HTTP 500.",
        "vision_findings": {
            "observations": ["Grafana dashboard shows payment error rate at 94%"],
            "extracted_text": "HTTP 500 Internal Server Error /api/v1/payments/charge",
        },
        "triage": {
            "category": "Infrastructure",
            "subcategory": "Payments",
            "urgency": "critical",
        },
        "escalation": {
            "required": True,
            "reason": "Major production payment outage affecting all customer transactions.",
        },
    }

    mock_cfg = Settings(TICKETING_MODE="mock", LLM_PROVIDER="mock")
    response = execute_escalation_workflow(payload, config=mock_cfg)

    assert response.status == "success"
    assert response.escalated is True
    # Upstream 'critical' urgency must map to Jira 'Highest' priority
    assert response.ticket.priority == "Highest"
    assert response.ticket.escalation_reason == "Major production payment outage affecting all customer transactions."


# ==============================================================================
# Scenario 4: Optional Data Missing (No screenshot, no RAG sources)
# ==============================================================================
def test_scenario_4_optional_data_missing():
    """
    No screenshot findings or retrieved sources are available.
    Component processes gracefully without inventing facts.
    """
    payload = {
        "case_id": "CASE-SCENARIO-4",
        "user_request": "Need a license assigned for MS Visio.",
        "escalation": {
            "required": True,
            "reason": "License provisioning requires administrator credentials.",
        },
    }

    mock_cfg = Settings(TICKETING_MODE="mock", LLM_PROVIDER="mock")
    response = execute_escalation_workflow(payload, config=mock_cfg)

    assert response.status == "success"
    assert response.escalated is True
    assert response.ticket.title is not None
    assert response.ticket.escalation_reason == "License provisioning requires administrator credentials."
    # Visual findings should indicate Not provided rather than invented claims
    desc = response.ticket.formatted_description
    assert "Observations: Not provided" in desc
    assert "**Sources Referenced:** Not provided" in desc


# ==============================================================================
# Scenario 5: Escalation Not Required (No ticket should be created)
# ==============================================================================
def test_scenario_5_escalation_not_required():
    """
    If escalation is false, no ticket should be created; status must be 'skipped'.
    """
    payload = {
        "case_id": "CASE-SCENARIO-5",
        "user_request": "How do I connect to office Wi-Fi?",
        "triage": {"category": "Network", "urgency": "low"},
        "resolution": {
            "status": "resolved",
            "attempted_steps": ["Provided Wi-Fi SSID and portal login steps"],
            "user_feedback": "Thanks, it works now!",
        },
        "escalation": {
            "required": False,
            "reason": "User resolved issue using automated instructions.",
        },
    }

    mock_cfg = Settings(TICKETING_MODE="mock")
    response = execute_escalation_workflow(payload, config=mock_cfg)

    assert response.status == "skipped"
    assert response.escalated is False
    assert response.ticket is None
    assert response.reason == "escalation_not_required"


# ==============================================================================
# Scenario 6: Malformed LLM Output (Validation fails safely or fallback fires)
# ==============================================================================
def test_scenario_6_malformed_llm_output_triggers_safe_fallback():
    """
    When the LLM produces malformed output, the workflow falls back safely to
    deterministic synthesis and succeeds without crashing or inventing facts.
    """
    payload = {
        "case_id": "CASE-SCENARIO-6",
        "user_request": "Database connection pool exhausted.",
        "triage": {"category": "Database", "urgency": "high"},
        "escalation": {
            "required": True,
            "reason": "Connection leak requires human investigation.",
        },
    }

    # Configure fallback=True
    cfg = Settings(
        TICKETING_MODE="mock",
        LLM_PROVIDER="custom",
        LLM_API_KEY="dummy",
        LLM_FALLBACK_ON_FAILURE=True,
    )

    with patch("llm_service.OpenAICompatibleLLMService.synthesize_ticket", side_effect=Exception("Invalid JSON syntax from LLM")):
        response = execute_escalation_workflow(payload, config=cfg)
        assert response.status == "success"
        assert response.escalated is True
        assert response.ticket.priority == "High"
        assert response.ticket.category == "Database"


def test_scenario_6_malformed_llm_output_fails_safely_when_fallback_disabled():
    """When fallback is disabled, malformed LLM output returns a structured error."""
    payload = {
        "case_id": "CASE-SCENARIO-6B",
        "user_request": "Database connection pool exhausted.",
        "escalation": {"required": True, "reason": "Connection leak"},
    }

    cfg = Settings(
        TICKETING_MODE="mock",
        LLM_PROVIDER="custom",
        LLM_API_KEY="dummy",
        LLM_FALLBACK_ON_FAILURE=False,
    )

    with patch("llm_service.OpenAICompatibleLLMService.synthesize_ticket", side_effect=Exception("Unparseable output")):
        response = execute_escalation_workflow(payload, config=cfg)
        assert response.status == "error"
        assert response.escalated is False
        assert "Unparseable output" in response.error


# ==============================================================================
# Scenario 7: Jira Failure (API rejects request or is unavailable)
# ==============================================================================
def test_scenario_7_jira_failure_returns_structured_error():
    """
    When Jira API rejects request (e.g. HTTP 400 Bad Request), workflow returns structured error.
    """
    payload = {
        "case_id": "CASE-SCENARIO-7",
        "user_request": "Cannot access shared drive S:\\.",
        "escalation": {"required": True, "reason": "Permission issue"},
    }

    jira_cfg = Settings(
        TICKETING_MODE="jira",
        JIRA_BASE_URL="https://test.atlassian.net",
        JIRA_EMAIL="user@test.com",
        JIRA_API_TOKEN="token123",
        JIRA_PROJECT_KEY="NONEXISTENT",
        JIRA_ISSUE_TYPE="Task",
    )

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "errorMessages": [],
            "errors": {"project": "Project 'NONEXISTENT' does not exist."},
        }
        mock_post.return_value = mock_resp

        response = execute_escalation_workflow(payload, config=jira_cfg)
        assert response.status == "error"
        assert response.escalated is False
        assert "Project 'NONEXISTENT' does not exist" in response.error


# ==============================================================================
# Scenario 8: Successful Mock Run
# ==============================================================================
def test_scenario_8_successful_mock_run():
    """
    Ticket is synthesized and returned with mock ID without external ticket creation.
    """
    payload = {
        "case_id": "CASE-SCENARIO-8",
        "user_request": "Docker container fails to start because port 8080 is already allocated.",
        "triage": {"category": "Docker", "urgency": "high"},
        "escalation": {
            "required": True,
            "reason": "The documented troubleshooting steps did not resolve the issue.",
        },
    }

    mock_cfg = Settings(TICKETING_MODE="mock")
    response = execute_escalation_workflow(payload, config=mock_cfg)

    assert response.status == "success"
    assert response.mode == "mock"
    assert response.escalated is True
    assert response.ticket.id == "MOCK-SCENARIO-8"
    assert "https://mock.jira.local/browse/" in response.ticket.url


# ==============================================================================
# Scenario 9: Successful Jira Run (Mocked HTTP response)
# ==============================================================================
def test_scenario_9_successful_jira_run():
    """
    Verifies field mapping and response handling for a successful Jira Cloud API creation.
    """
    payload = {
        "case_id": "CASE-SCENARIO-9",
        "user_request": "Kubernetes pod is crashlooping due to ConfigMap missing key.",
        "triage": {
            "category": "Kubernetes",
            "urgency": "critical",
        },
        "escalation": {
            "required": True,
            "reason": "Missing production ConfigMap key blocks deployment.",
        },
    }

    jira_cfg = Settings(
        TICKETING_MODE="jira",
        JIRA_BASE_URL="https://prod.atlassian.net",
        JIRA_EMAIL="ops@prod.com",
        JIRA_API_TOKEN="secret-token-xyz",
        JIRA_PROJECT_KEY="OPS",
        JIRA_ISSUE_TYPE="Incident",
    )

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "id": "2001",
            "key": "OPS-101",
            "self": "https://prod.atlassian.net/rest/api/3/issue/2001",
        }
        mock_post.return_value = mock_resp

        response = execute_escalation_workflow(payload, config=jira_cfg)

        assert response.status == "success"
        assert response.mode == "jira"
        assert response.escalated is True
        assert response.ticket.id == "2001"
        assert response.ticket.key == "OPS-101"
        assert response.ticket.url == "https://prod.atlassian.net/browse/OPS-101"
        assert response.ticket.priority == "Highest"

        # Verify posted payload structure
        call_kwargs = mock_post.call_args[1]
        sent_json = call_kwargs["json"]
        assert sent_json["fields"]["project"]["key"] == "OPS"
        assert sent_json["fields"]["issuetype"]["name"] == "Incident"
        assert sent_json["fields"]["priority"]["name"] == "Highest"
        assert sent_json["fields"]["description"]["type"] == "doc"
