"""
Main escalation workflow orchestrator.
Executes the full pipeline:
  Input JSON
  -> Input validation and normalization
  -> Escalation decision check
  -> LLM ticket synthesis
  -> Structured output validation
  -> Jira payload mapping
  -> Jira API or mock ticket sink
  -> Structured response
"""

import logging
from typing import Any, Dict, Optional, Union

from config import Settings, settings
from input_processor import (
    InputValidationError,
    MissingEscalationError,
    validate_and_normalize_input,
)
from llm_service import (
    LLMServiceError,
    generate_deterministic_ticket,
    get_llm_service,
)
from schemas import (
    EscalationResponse,
    LLMTicketOutput,
    TicketDetails,
)
from ticket_formatter import (
    PriorityMappingError,
    build_jira_issue_payload,
)
from jira_service import (
    JiraConfigurationError,
    JiraService,
    JiraServiceError,
)

logger = logging.getLogger(__name__)


def execute_escalation_workflow(
    raw_payload: Union[Dict[str, Any], str],
    config: Optional[Settings] = None,
) -> EscalationResponse:
    """
    Executes the end-to-end escalation and ticket creation workflow.

    Args:
        raw_payload: Input dictionary or raw JSON string.
        config: Optional configuration overrides (defaults to global settings).

    Returns:
        EscalationResponse object with execution status, mode, and ticket details.
    """
    cfg = config or settings
    mode = "mock" if cfg.is_mock_mode() else "jira"

    logger.info("Starting escalation workflow (Mode: %s)", mode)

    # --------------------------------------------------------------------------
    # Step 1: Validate and Normalize Input
    # --------------------------------------------------------------------------
    try:
        normalized_case = validate_and_normalize_input(raw_payload)
    except MissingEscalationError as exc:
        logger.warning("Workflow rejected: %s", exc)
        return EscalationResponse(
            status="error",
            mode=mode,
            escalated=False,
            error=str(exc),
            details={"error_type": "MissingEscalationError"},
        )
    except InputValidationError as exc:
        logger.warning("Input validation failed: %s", exc)
        return EscalationResponse(
            status="error",
            mode=mode,
            escalated=False,
            error=str(exc),
            details={"error_type": "InputValidationError"},
        )
    except Exception as exc:
        logger.error("Unexpected error during input processing: %s", exc, exc_info=True)
        return EscalationResponse(
            status="error",
            mode=mode,
            escalated=False,
            error=f"Unexpected input processing error: {exc}",
            details={"error_type": type(exc).__name__},
        )

    case_id = normalized_case.case_id

    # --------------------------------------------------------------------------
    # Step 2: Check Escalation Decision (Upstream Authority)
    # --------------------------------------------------------------------------
    if not normalized_case.escalation_required:
        logger.info(
            "Case %s does not require escalation. Skipping ticket creation.",
            case_id,
        )
        return EscalationResponse(
            status="skipped",
            mode=mode,
            escalated=False,
            case_id=case_id,
            reason="escalation_not_required",
            details={
                "message": "Upstream workflow indicated escalation is not required.",
                "user_request": normalized_case.user_request,
            },
        )

    logger.info(
        "Case %s requires escalation (Reason: %s)",
        case_id,
        normalized_case.escalation_reason,
    )

    # --------------------------------------------------------------------------
    # Step 3: LLM Ticket Synthesis & Validation
    # --------------------------------------------------------------------------
    llm_service = get_llm_service(cfg)
    try:
        ticket_output: LLMTicketOutput = llm_service.synthesize_ticket(normalized_case)
    except Exception as exc:
        logger.error("Synthesis error for case %s: %s", case_id, exc)
        if cfg.LLM_FALLBACK_ON_FAILURE:
            logger.info("Using deterministic fallback formatter for case %s", case_id)
            ticket_output = generate_deterministic_ticket(normalized_case)
        else:
            return EscalationResponse(
                status="error",
                mode=mode,
                escalated=False,
                case_id=case_id,
                error=f"LLM ticket synthesis failed: {exc}",
                details={"error_type": type(exc).__name__},
            )

    # --------------------------------------------------------------------------
    # Step 4: Map Ticket to Jira Payload
    # --------------------------------------------------------------------------
    try:
        project_key = cfg.JIRA_PROJECT_KEY or "IT"
        jira_payload = build_jira_issue_payload(
            ticket=ticket_output,
            case=normalized_case,
            project_key=project_key,
            issue_type=cfg.JIRA_ISSUE_TYPE,
            api_version=cfg.JIRA_API_VERSION,
        )
    except PriorityMappingError as exc:
        logger.error("Priority mapping failed for case %s: %s", case_id, exc)
        return EscalationResponse(
            status="error",
            mode=mode,
            escalated=False,
            case_id=case_id,
            error=str(exc),
            details={"error_type": "PriorityMappingError"},
        )
    except Exception as exc:
        logger.error("Payload formatting failed for case %s: %s", case_id, exc)
        return EscalationResponse(
            status="error",
            mode=mode,
            escalated=False,
            case_id=case_id,
            error=f"Failed to build Jira issue payload: {exc}",
            details={"error_type": type(exc).__name__},
        )

    # --------------------------------------------------------------------------
    # Step 5: Create Ticket in Jira (or Mock Sink)
    # --------------------------------------------------------------------------
    jira_service = JiraService(cfg)

    if cfg.is_mock_mode():
        # Simulated creation
        ticket_result = jira_service.create_mock_issue(
            case_id=case_id,
            summary=ticket_output.ticket_title,
        )
    else:
        # Real Jira Cloud API creation
        try:
            ticket_result = jira_service.create_jira_issue(jira_payload)
        except JiraConfigurationError as exc:
            return EscalationResponse(
                status="error",
                mode=mode,
                escalated=False,
                case_id=case_id,
                error=str(exc),
                details={"error_type": "JiraConfigurationError"},
            )
        except JiraServiceError as exc:
            return EscalationResponse(
                status="error",
                mode=mode,
                escalated=False,
                case_id=case_id,
                error=str(exc),
                details={"error_type": type(exc).__name__},
            )
        except Exception as exc:
            return EscalationResponse(
                status="error",
                mode=mode,
                escalated=False,
                case_id=case_id,
                error=f"Unexpected error creating Jira ticket: {exc}",
                details={"error_type": type(exc).__name__},
            )

    # --------------------------------------------------------------------------
    # Step 6: Construct Final Structured Response
    # --------------------------------------------------------------------------
    ticket_details = TicketDetails(
        id=ticket_result["id"],
        key=ticket_result.get("key"),
        url=ticket_result.get("url"),
        title=ticket_output.ticket_title,
        priority=ticket_output.priority_level,
        category=ticket_output.category,
        summary=ticket_output.summary,
        formatted_description=ticket_output.formatted_description,
        attempted_actions=ticket_output.attempted_actions,
        escalation_reason=ticket_output.escalation_reason,
        suggested_assignee_group=ticket_output.suggested_assignee_group,
        labels=ticket_output.labels,
    )

    logger.info("Successfully completed escalation workflow for case %s (Ticket ID: %s)", case_id, ticket_result["id"])

    return EscalationResponse(
        status="success",
        mode=mode,
        escalated=True,
        case_id=case_id,
        ticket=ticket_details,
        details={
            "mock_mode": cfg.is_mock_mode(),
            "jira_url": ticket_result.get("url"),
        },
    )


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    input_file = sys.argv[1] if len(sys.argv) > 1 else "mock_input.json"
    file_path = Path(input_file)

    if not file_path.exists():
        print(f"Error: Input file '{input_file}' not found.")
        sys.exit(1)

    print(f"Executing escalation workflow on '{input_file}'...")
    with open(file_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    result = execute_escalation_workflow(payload)
    print(json.dumps(result.model_dump(), indent=2))

