"""
Input processing and validation module.
Validates raw payloads against the input contract and normalizes data safely.
"""

import json
import uuid
from typing import Any, Dict, Union
from pydantic import ValidationError

from schemas import CaseInputPayload, NormalizedCase


class InputValidationError(Exception):
    """Raised when incoming JSON is invalid or fails schema validation."""
    pass


class MissingEscalationError(InputValidationError):
    """Raised when the upstream workflow fails to provide an explicit escalation decision."""
    pass


def validate_and_normalize_input(raw_data: Union[str, Dict[str, Any]]) -> NormalizedCase:
    """
    Validates the raw incoming data and normalizes it into a NormalizedCase.

    Args:
        raw_data: Dictionary or JSON string representing the incident payload.

    Returns:
        NormalizedCase with safe defaults for missing optional fields.

    Raises:
        InputValidationError: If JSON is malformed or required fields are missing.
        MissingEscalationError: If the escalation decision is omitted entirely.
    """
    # 1. Parse JSON if string
    if isinstance(raw_data, str):
        try:
            parsed_data = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise InputValidationError(f"Invalid JSON payload: {exc.msg} at line {exc.lineno}") from exc
    elif isinstance(raw_data, dict):
        parsed_data = raw_data
    else:
        raise InputValidationError(f"Expected dict or JSON string, got {type(raw_data).__name__}")

    # 2. Check explicitly for escalation decision before pydantic validation
    if "escalation" not in parsed_data or parsed_data.get("escalation") is None:
        raise MissingEscalationError(
            "Missing escalation decision. Upstream workflow must explicitly specify "
            "'escalation': {'required': bool, 'reason': ...}. This component does not make "
            "independent escalation decisions."
        )

    if not isinstance(parsed_data["escalation"], dict) or "required" not in parsed_data["escalation"]:
        raise MissingEscalationError(
            "The 'escalation' field must be an object with a boolean 'required' field."
        )

    # 3. Validate against Pydantic schema
    try:
        payload = CaseInputPayload(**parsed_data)
    except ValidationError as exc:
        # Format Pydantic errors into clear, actionable messages
        error_msgs = []
        for err in exc.errors():
            loc = " -> ".join(str(l) for l in err["loc"])
            error_msgs.append(f"Field '{loc}': {err['msg']}")
        raise InputValidationError(f"Input validation failed: {'; '.join(error_msgs)}") from exc

    # 4. Normalize fields gracefully without inventing facts
    case_id = payload.case_id.strip() if (payload.case_id and payload.case_id.strip()) else f"CASE-{uuid.uuid4().hex[:6].upper()}"

    # Vision findings
    vision_obs = payload.vision_findings.observations if payload.vision_findings else []
    vision_ocr = payload.vision_findings.extracted_text if payload.vision_findings else None
    vision_conf = payload.vision_findings.confidence if payload.vision_findings else None

    # Triage info
    triage_cat = (payload.triage.category.strip() if (payload.triage and payload.triage.category and payload.triage.category.strip()) else "General IT")
    triage_subcat = payload.triage.subcategory.strip() if (payload.triage and payload.triage.subcategory and payload.triage.subcategory.strip()) else None
    triage_urg = (payload.triage.urgency.strip().lower() if (payload.triage and payload.triage.urgency and payload.triage.urgency.strip()) else "medium")

    # RAG findings
    rag_sources = payload.rag.sources if (payload.rag and payload.rag.sources) else []
    rag_findings = payload.rag.findings if (payload.rag and payload.rag.findings) else []

    # Resolution attempt
    res_status = payload.resolution.status if payload.resolution else None
    res_steps = payload.resolution.attempted_steps if (payload.resolution and payload.resolution.attempted_steps) else []
    res_feedback = payload.resolution.user_feedback if payload.resolution else None

    # Escalation
    esc_req = payload.escalation.required
    esc_reason = (payload.escalation.reason.strip() if (payload.escalation.reason and payload.escalation.reason.strip()) else "Escalation requested by upstream workflow.")

    return NormalizedCase(
        case_id=case_id,
        user_request=payload.user_request,
        vision_observations=vision_obs,
        vision_extracted_text=vision_ocr,
        vision_confidence=vision_conf,
        triage_category=triage_cat,
        triage_subcategory=triage_subcat,
        triage_urgency=triage_urg,
        rag_sources=rag_sources,
        rag_findings=rag_findings,
        resolution_status=res_status,
        resolution_attempted_steps=res_steps,
        resolution_user_feedback=res_feedback,
        escalation_required=esc_req,
        escalation_reason=esc_reason,
    )
