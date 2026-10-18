"""
FastAPI HTTP Service for the Escalation and Jira Ticket-Creation Workflow.
Provides REST endpoints easily callable from n8n HTTP Request nodes or external services.
"""

import logging
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from input_processor import validate_and_normalize_input
from llm_service import generate_deterministic_ticket, get_llm_service
from schemas import EscalationResponse
from ticket_formatter import build_jira_issue_payload
from workflow import execute_escalation_workflow

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("escalation_api")

app = FastAPI(
    title="Multimodal AI IT Support - Escalation Service",
    description="Synthesizes escalated IT support cases using an LLM and creates tickets in Jira Cloud or Mock sink.",
    version="1.0.0",
)

# Enable CORS for local testing / n8n
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["System"])
async def root():
    """Root endpoint welcoming users and pointing to Swagger documentation."""
    return {
        "service": "Multimodal AI IT Support - Escalation Service",
        "status": "online",
        "interactive_docs": "/docs",
        "health_check": "/health",
        "ticketing_mode": settings.TICKETING_MODE,
        "llm_provider": settings.LLM_PROVIDER,
    }


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint reporting configuration status and operating mode."""
    jira_validation = settings.validate_jira_config()
    return {
        "status": "healthy",
        "ticketing_mode": settings.TICKETING_MODE,
        "is_mock_mode": settings.is_mock_mode(),
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "jira_configured": jira_validation is None,
        "jira_status": "Ready" if jira_validation is None else jira_validation,
    }


@app.post(
    "/escalate",
    response_model=EscalationResponse,
    status_code=status.HTTP_200_OK,
    tags=["Workflow"],
    summary="Process IT support case and create Jira ticket if escalation is required",
)
async def escalate_case(payload: Dict[str, Any]):
    """
    Main endpoint for the n8n workflow.

    Accepts structured IT case data, synthesizes an incident ticket using an LLM,
    and creates a ticket in Jira Cloud (or returns a mock ticket).
    """
    try:
        response = execute_escalation_workflow(payload, config=settings)
        # Return 200 with structured status
        return response
    except Exception as exc:
        logger.error("Unhandled error in /escalate: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "mode": settings.TICKETING_MODE,
                "escalated": False,
                "error": f"Internal server error: {exc}",
                "details": {"exception_type": type(exc).__name__},
            },
        )


@app.post(
    "/format-preview",
    tags=["Workflow"],
    summary="Preview synthesized ticket and Jira payload without calling Jira",
)
async def preview_ticket(payload: Dict[str, Any]):
    """
    Development endpoint: validates input and returns the generated ticket
    and full Jira payload without submitting to Jira or creating a mock issue.
    """
    try:
        case = validate_and_normalize_input(payload)
        llm = get_llm_service(settings)
        try:
            ticket = llm.synthesize_ticket(case)
        except Exception:
            ticket = generate_deterministic_ticket(case)

        jira_payload = build_jira_issue_payload(
            ticket=ticket,
            case=case,
            project_key=settings.JIRA_PROJECT_KEY or "IT",
            issue_type=settings.JIRA_ISSUE_TYPE,
            api_version=settings.JIRA_API_VERSION,
        )

        return {
            "status": "success",
            "case_id": case.case_id,
            "escalation_required": case.escalation_required,
            "synthesized_ticket": ticket.model_dump(),
            "jira_payload": jira_payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
