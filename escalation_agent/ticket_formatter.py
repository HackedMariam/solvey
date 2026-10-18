"""
Ticket formatting module.
Converts structured LLM outputs into Jira REST API payloads,
including Atlassian Document Format (ADF) for Jira Cloud v3 and legacy formatting for v2.
"""

import re
from typing import Any, Dict, List, Optional
from config import DEFAULT_PRIORITY_MAPPING
from schemas import LLMTicketOutput, NormalizedCase


class PriorityMappingError(Exception):
    """Raised when priority mapping is invalid or unresolvable."""
    pass


def map_to_jira_priority(priority_name: str, priority_map: Optional[Dict[str, str]] = None) -> str:
    """
    Maps an incoming priority or urgency level to a valid Jira priority string.
    Raises PriorityMappingError if the priority is not recognized.
    """
    mapping = priority_map or DEFAULT_PRIORITY_MAPPING
    clean_p = (priority_name or "").strip().lower()

    # Direct match in lowercase mapping
    if clean_p in mapping:
        return mapping[clean_p]

    # Check if priority_name is already a standard Jira priority (case-insensitive)
    for k, jira_name in mapping.items():
        if clean_p == jira_name.lower():
            return jira_name

    # If completely unrecognized, raise a clear error
    raise PriorityMappingError(
        f"Unable to map priority '{priority_name}' to a recognized Jira priority level. "
        f"Available priority mappings: {list(mapping.values())}."
    )


def sanitize_jira_labels(labels: List[str]) -> List[str]:
    """
    Sanitize labels for Jira (no spaces, special characters, max 255 chars).
    """
    sanitized = []
    for label in labels:
        clean = re.sub(r"[^a-zA-Z0-9_\-]", "", label.strip())
        if clean and clean not in sanitized:
            sanitized.append(clean[:50])
    return sanitized or ["escalation"]


def build_adf_description(ticket: LLMTicketOutput, case: NormalizedCase) -> Dict[str, Any]:
    """
    Builds Jira Cloud Atlassian Document Format (ADF) representation of the ticket.
    Jira Cloud REST API v3 requires ADF for rich-text issue descriptions.
    """
    doc_content: List[Dict[str, Any]] = []

    # 1. Incident Overview Header
    doc_content.append({
        "type": "heading",
        "attrs": {"level": 2},
        "content": [{"type": "text", "text": "Incident Overview"}]
    })
    overview_text = (
        f"Case ID: {case.case_id}\n"
        f"Category: {ticket.category}\n"
        f"Preserved Urgency: {case.triage_urgency.capitalize()} (Priority: {ticket.priority_level})\n"
        f"Summary: {ticket.summary}"
    )
    doc_content.append({
        "type": "paragraph",
        "content": [{"type": "text", "text": overview_text}]
    })

    # 2. User Problem Description
    doc_content.append({
        "type": "heading",
        "attrs": {"level": 3},
        "content": [{"type": "text", "text": "User Request"}]
    })
    doc_content.append({
        "type": "paragraph",
        "content": [{"type": "text", "text": case.user_request}]
    })

    # 3. Visual Findings & OCR (if provided)
    if case.vision_observations or case.vision_extracted_text:
        doc_content.append({
            "type": "heading",
            "attrs": {"level": 3},
            "content": [{"type": "text", "text": "Visual Findings & Terminal OCR"}]
        })
        if case.vision_observations:
            list_items = []
            for obs in case.vision_observations:
                list_items.append({
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": obs}]}]
                })
            doc_content.append({"type": "bulletList", "content": list_items})

        if case.vision_extracted_text:
            doc_content.append({
                "type": "codeBlock",
                "attrs": {"language": "text"},
                "content": [{"type": "text", "text": case.vision_extracted_text}]
            })

    # 4. Diagnostic Documentation / RAG (if provided)
    if case.rag_sources or case.rag_findings:
        doc_content.append({
            "type": "heading",
            "attrs": {"level": 3},
            "content": [{"type": "text", "text": "Retrieved Technical Documentation (RAG)"}]
        })
        if case.rag_sources:
            doc_content.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": f"Sources: {', '.join(case.rag_sources)}"}]
            })
        if case.rag_findings:
            list_items = []
            for finding in case.rag_findings:
                list_items.append({
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": finding}]}]
                })
            doc_content.append({"type": "bulletList", "content": list_items})

    # 5. Attempted Troubleshooting & Outcomes
    doc_content.append({
        "type": "heading",
        "attrs": {"level": 3},
        "content": [{"type": "text", "text": "Attempted Troubleshooting & Outcomes"}]
    })
    if ticket.attempted_actions:
        list_items = []
        for act in ticket.attempted_actions:
            list_items.append({
                "type": "listItem",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": act}]}]
            })
        doc_content.append({"type": "bulletList", "content": list_items})
    else:
        doc_content.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": "No previous troubleshooting steps reported."}]
        })

    # 6. Reason for Escalation (Panel / Callout)
    doc_content.append({
        "type": "heading",
        "attrs": {"level": 3},
        "content": [{"type": "text", "text": "Reason for Escalation"}]
    })
    doc_content.append({
        "type": "panel",
        "attrs": {"panelType": "warning"},
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": ticket.escalation_reason}]
            }
        ]
    })

    # 7. Assignment Note
    doc_content.append({
        "type": "paragraph",
        "content": [
            {
                "type": "text",
                "text": f"Suggested Assignee Group: {ticket.suggested_assignee_group} (informational only)"
            }
        ]
    })

    return {
        "version": 1,
        "type": "doc",
        "content": doc_content,
    }


def build_plain_description(ticket: LLMTicketOutput, case: NormalizedCase) -> str:
    """Build a clean plain-text/markdown description for Jira REST API v2 or mock display."""
    return ticket.formatted_description


def build_jira_issue_payload(
    ticket: LLMTicketOutput,
    case: NormalizedCase,
    project_key: str,
    issue_type: str = "Task",
    api_version: str = "3",
    priority_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Constructs the exact JSON payload expected by Jira's POST /rest/api/{version}/issue endpoint.

    Args:
        ticket: Validated LLM ticket synthesis.
        case: Normalized input case facts.
        project_key: Jira project key (e.g. 'IT').
        issue_type: Jira issue type (e.g. 'Task').
        api_version: '3' for ADF (default) or '2' for plain string.
        priority_map: Optional custom priority mapping.

    Returns:
        Dictionary conforming to Jira Cloud issue creation schema.
    """
    if not project_key or not project_key.strip():
        raise ValueError("Jira project_key cannot be empty.")

    jira_priority = map_to_jira_priority(ticket.priority_level, priority_map)
    sanitized_labels = sanitize_jira_labels(ticket.labels)

    # Jira summaries are limited to 255 characters
    summary_text = ticket.ticket_title[:250].strip()

    fields: Dict[str, Any] = {
        "project": {"key": project_key.strip().upper()},
        "summary": summary_text,
        "issuetype": {"name": issue_type.strip()},
        "priority": {"name": jira_priority},
        "labels": sanitized_labels,
    }

    if api_version == "3":
        fields["description"] = build_adf_description(ticket, case)
    else:
        fields["description"] = build_plain_description(ticket, case)

    return {"fields": fields}
