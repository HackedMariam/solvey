"""
Data schemas and validation models using Pydantic v2.
Defines input contract, LLM structured output, Jira payload models, and API responses.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ==============================================================================
# 1. Upstream Input Schemas
# ==============================================================================

class VisionFindings(BaseModel):
    """Visual evidence extracted from screenshots or PDFs."""
    observations: List[str] = Field(
        default_factory=list,
        description="List of factual observations from visual analysis"
    )
    extracted_text: Optional[str] = Field(
        default=None,
        description="OCR text extracted from terminal, dialog, or logs"
    )
    confidence: Optional[float] = Field(
        default=None,
        description="Confidence score between 0.0 and 1.0"
    )


class TriageInfo(BaseModel):
    """Categorization and urgency determined by upstream triage."""
    category: Optional[str] = Field(
        default=None,
        description="Incident category (e.g., Docker, Network, Database)"
    )
    subcategory: Optional[str] = Field(
        default=None,
        description="Incident subcategory (e.g., Port conflict, Permission)"
    )
    urgency: Optional[str] = Field(
        default=None,
        description="Urgency level assigned upstream: critical, high, medium, low"
    )
    confidence: Optional[float] = Field(
        default=None,
        description="Confidence score between 0.0 and 1.0"
    )


class RAGFindings(BaseModel):
    """Technical documentation retrieved by upstream RAG component."""
    status: Optional[str] = Field(
        default=None,
        description="Retrieval status: documents_found, no_documents_found, failed"
    )
    document_count: Optional[int] = Field(
        default=0,
        description="Number of relevant documents found"
    )
    sources: List[str] = Field(
        default_factory=list,
        description="Source document titles or identifiers"
    )
    findings: List[str] = Field(
        default_factory=list,
        description="Key findings or recommendations retrieved from documentation"
    )


class ResolutionAttempt(BaseModel):
    """Troubleshooting steps previously attempted and reported outcome."""
    status: Optional[str] = Field(
        default=None,
        description="Outcome of troubleshooting attempts: failed, partial, resolved"
    )
    attempted_steps: List[str] = Field(
        default_factory=list,
        description="Troubleshooting actions performed prior to escalation"
    )
    user_feedback: Optional[str] = Field(
        default=None,
        description="Feedback from user on why resolution failed"
    )


class EscalationDecision(BaseModel):
    """Explicit escalation decision from upstream workflow."""
    required: bool = Field(
        ...,
        description="True if escalation to a human IT technician is required"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Documented rationale for escalating"
    )


class CaseInputPayload(BaseModel):
    """
    Main incoming JSON payload from upstream workflow (e.g. n8n).
    Strictly requires user_request and escalation decision.
    """
    case_id: Optional[str] = Field(
        default=None,
        description="Unique case identifier (e.g., CASE-001)"
    )
    user_request: str = Field(
        ...,
        description="The primary user issue description"
    )
    vision_findings: Optional[VisionFindings] = Field(
        default=None,
        description="Visual evidence from screenshot/PDF"
    )
    triage: Optional[TriageInfo] = Field(
        default=None,
        description="Upstream triage category and urgency"
    )
    rag: Optional[RAGFindings] = Field(
        default=None,
        description="Technical documentation findings"
    )
    resolution: Optional[ResolutionAttempt] = Field(
        default=None,
        description="Troubleshooting steps previously tried"
    )
    escalation: EscalationDecision = Field(
        ...,
        description="Explicit escalation decision made by upstream workflow"
    )

    @field_validator("user_request")
    @classmethod
    def user_request_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_request cannot be empty")
        return v.strip()


# ==============================================================================
# 2. Normalized Case (Safe Internal Representation)
# ==============================================================================

class NormalizedCase(BaseModel):
    """Normalized case data ready for LLM synthesis and formatting."""
    case_id: str
    user_request: str
    vision_observations: List[str]
    vision_extracted_text: Optional[str]
    vision_confidence: Optional[float]
    triage_category: str
    triage_subcategory: Optional[str]
    triage_urgency: str
    rag_sources: List[str]
    rag_findings: List[str]
    resolution_status: Optional[str]
    resolution_attempted_steps: List[str]
    resolution_user_feedback: Optional[str]
    escalation_required: bool
    escalation_reason: str


# ==============================================================================
# 3. LLM Structured Output Schema
# ==============================================================================

class LLMTicketOutput(BaseModel):
    """
    Structured output generated by the LLM for ticket synthesis.
    Strictly follows the prompt's required output contract.
    """
    ticket_title: str = Field(
        ...,
        description="Concise incident title"
    )
    priority_level: str = Field(
        ...,
        description="Jira-compatible priority matching upstream urgency (e.g. Highest, High, Medium, Low)"
    )
    category: str = Field(
        ...,
        description="Incident category"
    )
    summary: str = Field(
        ...,
        description="Brief description of the issue"
    )
    formatted_description: str = Field(
        ...,
        description="Structured ticket description in human-readable markdown"
    )
    attempted_actions: List[str] = Field(
        default_factory=list,
        description="List of actions and reported outcomes already attempted"
    )
    escalation_reason: str = Field(
        ...,
        description="Why human intervention is required"
    )
    suggested_assignee_group: str = Field(
        default="IT Support",
        description="Suggested technician group (suggestion only, not assigned automatically)"
    )
    labels: List[str] = Field(
        default_factory=list,
        description="Labels for issue tagging (e.g., docker, escalation)"
    )

    @field_validator("ticket_title", "summary", "escalation_reason")
    @classmethod
    def non_empty_strings(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


# ==============================================================================
# 4. Jira Output & API Response Schemas
# ==============================================================================

class TicketDetails(BaseModel):
    """Structured details of the created or simulated ticket."""
    id: str = Field(..., description="Ticket identifier (e.g. Jira key or MOCK-001)")
    key: Optional[str] = Field(default=None, description="Jira issue key if created in Jira")
    url: Optional[str] = Field(default=None, description="Direct URL to browse the issue")
    title: str = Field(..., description="Ticket title / summary")
    priority: str = Field(..., description="Assigned priority level")
    category: str = Field(..., description="Incident category")
    summary: str = Field(..., description="Summary paragraph")
    formatted_description: Optional[str] = Field(default=None, description="Detailed markdown description")
    attempted_actions: List[str] = Field(default_factory=list)
    escalation_reason: str = Field(...)
    suggested_assignee_group: str = Field(default="IT Support")
    labels: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EscalationResponse(BaseModel):
    """Standardized response returned to caller (n8n, API client, or test)."""
    status: str = Field(
        ...,
        description="Status: 'success', 'skipped', or 'error'"
    )
    mode: str = Field(
        ...,
        description="Execution mode: 'mock' or 'jira'"
    )
    escalated: bool = Field(
        ...,
        description="Whether an escalation ticket was created or mock-generated"
    )
    case_id: Optional[str] = Field(default=None)
    reason: Optional[str] = Field(
        default=None,
        description="Explanation if skipped or high-level status reason"
    )
    ticket: Optional[TicketDetails] = Field(
        default=None,
        description="Ticket details when escalated"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if status is 'error'"
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional debugging or diagnostic details"
    )
