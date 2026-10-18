"""
LLM integration service for ticket synthesis.
Supports modular providers (Mock, OpenAI, Gemini/compatible), structured JSON output,
strict schema validation, and deterministic fallback formatting.
"""

import json
import logging
import re
from typing import Any, Dict, Optional
from pydantic import ValidationError

from config import DEFAULT_PRIORITY_MAPPING, Settings, settings
from schemas import LLMTicketOutput, NormalizedCase

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an IT support ticket-writing assistant.

Your task is to transform the supplied incident data into a clear, factual, professional support ticket for a human IT technician.

Use only the information present in the input payload.

Summarize the original problem, relevant visual evidence, triage findings, retrieved documentation, troubleshooting actions already attempted, their reported outcomes, and the reason for escalation.

Distinguish confirmed observations from possible explanations. Do not present a suspected cause as a confirmed diagnosis.

Do not invent technical details, error messages, commands, sources, user actions, or resolution steps.

Do not recommend risky actions or attempt to resolve the incident yourself.

Preserve the urgency assigned by the upstream triage component. Do not increase or decrease it based on your own interpretation.

If information is missing, indicate that it was not provided. Do not fabricate an assignee or claim that a ticket has been created.

Return only a valid JSON object matching the required output schema."""

OUTPUT_SCHEMA_INSTRUCTION = """
You MUST respond with a single, valid JSON object matching this exact schema:
{
  "ticket_title": "Concise incident title (e.g. [Docker] Port 8080 conflict during startup)",
  "priority_level": "Jira priority: Highest, High, Medium, or Low (must match upstream urgency)",
  "category": "Incident category from triage or user request",
  "summary": "Brief factual description of the issue",
  "formatted_description": "Detailed structured markdown description for IT technician",
  "attempted_actions": ["Action and reported outcome"],
  "escalation_reason": "Why human intervention is required",
  "suggested_assignee_group": "IT Support",
  "labels": ["category-tag", "escalation"]
}
"""


class LLMServiceError(Exception):
    """Base error for LLM synthesis failures."""
    pass


def map_urgency_to_priority(urgency: str) -> str:
    """Safely map upstream urgency to a Jira-compatible priority string."""
    urg = (urgency or "medium").strip().lower()
    return DEFAULT_PRIORITY_MAPPING.get(urg, "Medium")


def generate_deterministic_ticket(case: NormalizedCase) -> LLMTicketOutput:
    """
    Deterministically formats an incident into a valid LLMTicketOutput schema.
    Guarantees zero hallucinations and preserves all raw facts when LLM is unavailable or fails.
    """
    priority = map_urgency_to_priority(case.triage_urgency)
    category = case.triage_category or "General IT"
    subcategory_part = f" - {case.triage_subcategory}" if case.triage_subcategory else ""
    title = f"[{category}{subcategory_part}] {case.user_request[:60]}..." if len(case.user_request) > 60 else f"[{category}{subcategory_part}] {case.user_request}"

    # Build attempted actions list
    actions = []
    if case.resolution_attempted_steps:
        for step in case.resolution_attempted_steps:
            outcome = f" (Status: {case.resolution_status})" if case.resolution_status else ""
            actions.append(f"{step}{outcome}")
    if case.resolution_user_feedback:
        actions.append(f"User reported feedback: {case.resolution_user_feedback}")

    if not actions:
        actions = ["No prior troubleshooting actions reported by upstream workflow."]

    # Build structured description markdown
    desc_lines = [
        f"### Incident Overview ({case.case_id})",
        f"- **Category:** {category}",
        f"- **Subcategory:** {case.triage_subcategory or 'Not provided'}",
        f"- **Preserved Urgency:** {case.triage_urgency.capitalize()}",
        f"- **Reported Problem:** {case.user_request}",
        "",
        "### Visual Findings (Screenshot / Document OCR)",
    ]

    if case.vision_observations:
        desc_lines.append("**Observations:**")
        for obs in case.vision_observations:
            desc_lines.append(f"- {obs}")
    else:
        desc_lines.append("- Observations: Not provided")

    if case.vision_extracted_text:
        desc_lines.append("\n**Extracted OCR / Terminal Text:**")
        desc_lines.append(f"```\n{case.vision_extracted_text}\n```")
    else:
        desc_lines.append("- Extracted OCR: Not provided")

    desc_lines.append("\n### Diagnostic Documentation (RAG)")
    if case.rag_sources:
        desc_lines.append(f"- **Sources Referenced:** {', '.join(case.rag_sources)}")
    else:
        desc_lines.append("- **Sources Referenced:** Not provided")

    if case.rag_findings:
        desc_lines.append("- **Documented Findings:**")
        for finding in case.rag_findings:
            desc_lines.append(f"  * {finding}")
    else:
        desc_lines.append("- **Documented Findings:** None returned by upstream RAG")

    desc_lines.append("\n### Troubleshooting History & Outcomes")
    if case.resolution_attempted_steps:
        desc_lines.append("**Attempted Steps:**")
        for s in case.resolution_attempted_steps:
            desc_lines.append(f"- {s}")
    else:
        desc_lines.append("- Attempted Steps: None recorded")

    if case.resolution_user_feedback:
        desc_lines.append(f"- **User Feedback:** {case.resolution_user_feedback}")

    desc_lines.append("\n### Reason for Escalation")
    desc_lines.append(f"> {case.escalation_reason}")

    # Build labels
    labels = ["escalation", "multimodal-ai"]
    clean_cat = re.sub(r"[^a-zA-Z0-9_-]", "", category.lower())
    if clean_cat and clean_cat not in labels:
        labels.append(clean_cat)

    return LLMTicketOutput(
        ticket_title=title,
        priority_level=priority,
        category=category,
        summary=case.user_request,
        formatted_description="\n".join(desc_lines),
        attempted_actions=actions,
        escalation_reason=case.escalation_reason,
        suggested_assignee_group="IT Support",
        labels=labels,
    )


def extract_json_from_llm_response(text: str) -> Dict[str, Any]:
    """Extract and parse JSON object from LLM output, handling markdown code fences and extraneous text."""
    cleaned = text.strip()

    # Search for markdown ```json ... ``` or ``` ... ``` block anywhere in the text
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    else:
        # If no code fence, attempt to find first '{' and last '}'
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx : end_idx + 1]

    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise LLMServiceError(f"LLM output is not a JSON object: {type(data).__name__}")
        return data
    except json.JSONDecodeError as exc:
        raise LLMServiceError(f"Failed to parse LLM JSON: {exc.msg}") from exc


class BaseLLMService:
    """Base interface for LLM ticket synthesis."""

    def synthesize_ticket(self, case: NormalizedCase) -> LLMTicketOutput:
        raise NotImplementedError


class MockLLMService(BaseLLMService):
    """
    Mock LLM service that synthesizes high-quality factual tickets
    without making external API calls. Ideal for tests and offline development.
    """

    def synthesize_ticket(self, case: NormalizedCase) -> LLMTicketOutput:
        logger.info("Synthesizing ticket using MockLLMService (deterministic)")
        return generate_deterministic_ticket(case)


class OpenAICompatibleLLMService(BaseLLMService):
    """
    LLM service that calls OpenAI or any OpenAI-compatible endpoint
    (including Google Gemini OpenAI endpoint, Groq, Ollama, vLLM).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
        timeout: int = 30,
        fallback_on_failure: bool = True,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.fallback_on_failure = fallback_on_failure

        try:
            from openai import OpenAI
            client_kwargs: Dict[str, Any] = {
                "api_key": self.api_key,
                "timeout": self.timeout,
            }
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self.client = OpenAI(**client_kwargs)
        except Exception as exc:
            raise LLMServiceError(f"Failed to initialize OpenAI client: {exc}") from exc

    def synthesize_ticket(self, case: NormalizedCase) -> LLMTicketOutput:
        case_data_json = case.model_dump_json(indent=2)
        expected_priority = map_urgency_to_priority(case.triage_urgency)

        user_content = (
            f"Here is the normalized incident case data:\n\n{case_data_json}\n\n"
            f"Note: Upstream urgency is '{case.triage_urgency}'. "
            f"You MUST set 'priority_level' to '{expected_priority}'.\n\n"
            f"{OUTPUT_SCHEMA_INSTRUCTION}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,  # Low temperature for factual fidelity
            )

            response_content = response.choices[0].message.content
            if not response_content:
                raise LLMServiceError("LLM returned empty response")

            raw_dict = extract_json_from_llm_response(response_content)

            # Enforce priority preservation
            raw_dict["priority_level"] = expected_priority

            # Validate against schema
            return LLMTicketOutput(**raw_dict)

        except Exception as exc:
            logger.warning("LLM API call or validation failed: %s", exc)
            if self.fallback_on_failure:
                logger.info("Using deterministic fallback formatter due to LLM failure")
                return generate_deterministic_ticket(case)
            raise LLMServiceError(f"LLM synthesis failed: {exc}") from exc


def get_llm_service(config: Optional[Settings] = None) -> BaseLLMService:
    """Factory function to build the appropriate LLM service according to settings."""
    cfg = config or settings
    provider = cfg.LLM_PROVIDER.lower().strip()

    if provider == "mock" or not cfg.LLM_API_KEY:
        return MockLLMService()

    if provider in ("openai", "gemini", "custom"):
        base_url = cfg.LLM_BASE_URL
        # Auto-configure base URL for Gemini if specified as gemini provider without custom URL
        if provider == "gemini" and not base_url:
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

        return OpenAICompatibleLLMService(
            api_key=cfg.LLM_API_KEY,
            model=cfg.LLM_MODEL,
            base_url=base_url,
            timeout=cfg.LLM_TIMEOUT_SECONDS,
            fallback_on_failure=cfg.LLM_FALLBACK_ON_FAILURE,
        )

    # Fallback to mock if unknown
    logger.warning("Unknown LLM provider '%s', defaulting to mock", provider)
    return MockLLMService()
