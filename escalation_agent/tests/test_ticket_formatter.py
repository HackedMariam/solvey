"""
Unit tests for ticket formatting and Jira payload construction.
"""

import pytest
from schemas import LLMTicketOutput, NormalizedCase
from ticket_formatter import (
    PriorityMappingError,
    build_adf_description,
    build_jira_issue_payload,
    map_to_jira_priority,
    sanitize_jira_labels,
)


@pytest.fixture
def sample_case() -> NormalizedCase:
    return NormalizedCase(
        case_id="CASE-001",
        user_request="Docker container fails to start due to port 8080 conflict.",
        vision_observations=["Terminal error shown"],
        vision_extracted_text="Bind for 0.0.0.0:8080 failed: port is already allocated",
        vision_confidence=0.95,
        triage_category="Docker",
        triage_subcategory="Port conflict",
        triage_urgency="high",
        rag_sources=["Docker Networking Guide"],
        rag_findings=["Another process may be using port 8080."],
        resolution_status="failed",
        resolution_attempted_steps=["Checked container logs", "Restarted Docker daemon"],
        resolution_user_feedback="Container still fails to start.",
        escalation_required=True,
        escalation_reason="Documented troubleshooting steps did not resolve the issue.",
    )


@pytest.fixture
def sample_ticket() -> LLMTicketOutput:
    return LLMTicketOutput(
        ticket_title="[Docker - Port conflict] Container fails to start port 8080 conflict",
        priority_level="High",
        category="Docker",
        summary="Docker container fails to start because port 8080 is already allocated.",
        formatted_description="### Incident Overview\nDocker port conflict...",
        attempted_actions=[
            "Checked container logs (Status: failed)",
            "Restarted Docker daemon (Status: failed)",
        ],
        escalation_reason="Documented troubleshooting steps did not resolve the issue.",
        suggested_assignee_group="IT Support",
        labels=["docker", "port-conflict", "escalation"],
    )


def test_priority_mapping_standard_values():
    """Verify that all standard upstream urgencies map to Jira priority names correctly."""
    assert map_to_jira_priority("critical") == "Highest"
    assert map_to_jira_priority("high") == "High"
    assert map_to_jira_priority("medium") == "Medium"
    assert map_to_jira_priority("low") == "Low"
    # Case insensitive
    assert map_to_jira_priority("CRITICAL") == "Highest"
    assert map_to_jira_priority("High") == "High"


def test_priority_mapping_unrecognized_raises_error():
    """Unrecognized priority without valid mapping must raise PriorityMappingError."""
    with pytest.raises(PriorityMappingError):
        map_to_jira_priority("super-ultra-critical")


def test_sanitize_jira_labels():
    """Ensure invalid characters and spaces are stripped from Jira labels."""
    labels = ["docker container", "escalation!", "rag_found", "docker container"]
    sanitized = sanitize_jira_labels(labels)
    assert "dockercontainer" in sanitized
    assert "escalation" in sanitized
    assert "rag_found" in sanitized
    # Duplicate check
    assert len(sanitized) == len(set(sanitized))


def test_adf_description_contains_expected_nodes(sample_ticket, sample_case):
    """Verify that the ADF structure complies with Jira Cloud requirements."""
    adf = build_adf_description(sample_ticket, sample_case)
    assert adf["type"] == "doc"
    assert adf["version"] == 1
    assert "content" in adf
    assert len(adf["content"]) > 0

    types = [node["type"] for node in adf["content"]]
    assert "heading" in types
    assert "paragraph" in types
    assert "bulletList" in types
    assert "codeBlock" in types
    assert "panel" in types


def test_build_jira_issue_payload_v3(sample_ticket, sample_case):
    """Verify complete Jira Cloud v3 payload structure."""
    payload = build_jira_issue_payload(
        ticket=sample_ticket,
        case=sample_case,
        project_key="IT",
        issue_type="Task",
        api_version="3",
    )

    fields = payload["fields"]
    assert fields["project"]["key"] == "IT"
    assert fields["issuetype"]["name"] == "Task"
    assert fields["priority"]["name"] == "High"
    assert fields["summary"] == sample_ticket.ticket_title[:250]
    assert fields["description"]["type"] == "doc"
    assert "escalation" in fields["labels"]
