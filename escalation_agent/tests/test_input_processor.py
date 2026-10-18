"""
Unit tests for input processing and validation.
"""

import pytest
from input_processor import (
    InputValidationError,
    MissingEscalationError,
    validate_and_normalize_input,
)


def test_valid_input_normalization():
    """Test standard valid payload with all fields populated."""
    raw = {
        "case_id": "CASE-101",
        "user_request": "Cannot connect to VPN from home.",
        "vision_findings": {
            "observations": ["Error 691 dialog displayed"],
            "extracted_text": "Authentication failure: invalid credentials",
            "confidence": 0.98,
        },
        "triage": {
            "category": "Network",
            "subcategory": "VPN",
            "urgency": "high",
            "confidence": 0.9,
        },
        "rag": {
            "status": "documents_found",
            "document_count": 1,
            "sources": ["VPN Guide"],
            "findings": ["Reset user network token"],
        },
        "resolution": {
            "status": "failed",
            "attempted_steps": ["Verified password", "Reinstalled client"],
            "user_feedback": "Still getting error 691",
        },
        "escalation": {
            "required": True,
            "reason": "VPN server rejected valid token.",
        },
    }

    case = validate_and_normalize_input(raw)
    assert case.case_id == "CASE-101"
    assert case.user_request == "Cannot connect to VPN from home."
    assert case.triage_category == "Network"
    assert case.triage_urgency == "high"
    assert case.escalation_required is True
    assert case.escalation_reason == "VPN server rejected valid token."
    assert len(case.vision_observations) == 1
    assert case.vision_extracted_text == "Authentication failure: invalid credentials"
    assert len(case.rag_sources) == 1
    assert len(case.resolution_attempted_steps) == 2


def test_missing_escalation_field_raises_error():
    """Component must not make independent escalation decisions; missing escalation must fail."""
    raw = {
        "case_id": "CASE-102",
        "user_request": "Printer is offline.",
    }
    with pytest.raises(MissingEscalationError) as exc_info:
        validate_and_normalize_input(raw)
    assert "Missing escalation decision" in str(exc_info.value)


def test_escalation_without_required_boolean_raises_error():
    """Escalation dict missing 'required' boolean must raise MissingEscalationError."""
    raw = {
        "case_id": "CASE-103",
        "user_request": "Printer is offline.",
        "escalation": {"reason": "Not working"},
    }
    with pytest.raises(MissingEscalationError):
        validate_and_normalize_input(raw)


def test_empty_user_request_raises_error():
    """Empty user_request must fail validation."""
    raw = {
        "user_request": "   ",
        "escalation": {"required": True},
    }
    with pytest.raises(InputValidationError):
        validate_and_normalize_input(raw)


def test_missing_optional_fields_handled_gracefully():
    """Minimal payload with only required fields must normalize safely with clear defaults."""
    raw = {
        "user_request": "Cannot launch spreadsheet program.",
        "escalation": {
            "required": True,
            "reason": "App crashes repeatedly on startup.",
        },
    }
    case = validate_and_normalize_input(raw)
    assert case.case_id.startswith("CASE-")
    assert case.user_request == "Cannot launch spreadsheet program."
    assert case.triage_category == "General IT"
    assert case.triage_urgency == "medium"
    assert case.vision_observations == []
    assert case.vision_extracted_text is None
    assert case.rag_sources == []
    assert case.resolution_attempted_steps == []
    assert case.escalation_required is True
    assert case.escalation_reason == "App crashes repeatedly on startup."


def test_invalid_json_string_raises_error():
    """Malformed JSON string input must raise InputValidationError."""
    with pytest.raises(InputValidationError) as exc:
        validate_and_normalize_input("{invalid_json: 123")
    assert "Invalid JSON payload" in str(exc.value)
