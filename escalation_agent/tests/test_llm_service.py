"""
Unit tests for LLM ticket synthesis and deterministic fallback formatting.
"""

import pytest
from llm_service import (
    MockLLMService,
    extract_json_from_llm_response,
    generate_deterministic_ticket,
    map_urgency_to_priority,
)
from schemas import NormalizedCase


@pytest.fixture
def sample_case():
    return NormalizedCase(
        case_id="CASE-404",
        user_request="PostgreSQL container crashed with OOMKilled",
        vision_observations=["Server monitor shows memory spike to 100%"],
        vision_extracted_text="Exit code 137: OOMKilled",
        vision_confidence=0.99,
        triage_category="Database",
        triage_subcategory="Crash",
        triage_urgency="critical",
        rag_sources=["Postgres Sizing Guide"],
        rag_findings=["Increase shared_buffers or container memory limit"],
        resolution_status="failed",
        resolution_attempted_steps=["Restarted container with default limits"],
        resolution_user_feedback="Crashes again within 2 minutes",
        escalation_required=True,
        escalation_reason="Database crashed with OOMKilled; requires infra sizing change.",
    )


def test_deterministic_ticket_generator_preserves_facts(sample_case):
    """Ensure deterministic formatter accurately includes all facts and preserves priority."""
    ticket = generate_deterministic_ticket(sample_case)

    # Urgency preservation
    assert ticket.priority_level == "Highest"  # 'critical' -> 'Highest'
    assert ticket.category == "Database"
    assert "PostgreSQL container crashed with OOMKilled" in ticket.summary
    assert ticket.escalation_reason == sample_case.escalation_reason
    assert "Exit code 137: OOMKilled" in ticket.formatted_description
    assert "Server monitor shows memory spike to 100%" in ticket.formatted_description
    assert "Postgres Sizing Guide" in ticket.formatted_description
    assert "Crashes again within 2 minutes" in str(ticket.attempted_actions)


def test_priority_mapping_cases():
    """Verify mapping of all triage urgency levels."""
    assert map_urgency_to_priority("critical") == "Highest"
    assert map_urgency_to_priority("high") == "High"
    assert map_urgency_to_priority("medium") == "Medium"
    assert map_urgency_to_priority("low") == "Low"
    assert map_urgency_to_priority(None) == "Medium"


def test_extract_json_from_llm_response_with_code_fences():
    """Test extracting JSON wrapped in markdown ```json ... ``` blocks."""
    raw_markdown = """
    Here is the ticket:
    ```json
    {
      "ticket_title": "Database Outage",
      "priority_level": "Highest",
      "category": "Database",
      "summary": "DB down",
      "formatted_description": "Full details...",
      "attempted_actions": ["Restart"],
      "escalation_reason": "Repeated crash",
      "suggested_assignee_group": "DBA",
      "labels": ["database", "escalation"]
    }
    ```
    """
    data = extract_json_from_llm_response(raw_markdown)
    assert data["ticket_title"] == "Database Outage"
    assert data["priority_level"] == "Highest"


def test_mock_llm_service(sample_case):
    """Test MockLLMService produces schema-compliant output."""
    service = MockLLMService()
    ticket = service.synthesize_ticket(sample_case)
    assert ticket.ticket_title is not None
    assert ticket.priority_level == "Highest"
    assert "Database" in ticket.category
