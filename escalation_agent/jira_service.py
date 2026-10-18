"""
Jira integration service.
Handles mock ticket generation and real Jira Cloud REST API interactions
with robust error classification, authentication, and safe network timeout handling.
"""

import base64
import logging
from typing import Any, Dict, Optional, Tuple
import requests

from config import Settings, settings

logger = logging.getLogger(__name__)


# ==============================================================================
# Exceptions
# ==============================================================================

class JiraServiceError(Exception):
    """Base error for all Jira interactions."""
    pass


class JiraConfigurationError(JiraServiceError):
    """Raised when Jira settings or credentials are not configured."""
    pass


class JiraAuthenticationError(JiraServiceError):
    """Raised on HTTP 401 or 403 authentication failures."""
    pass


class JiraValidationError(JiraServiceError):
    """Raised when Jira rejects the payload (e.g., invalid project, issue type, or fields)."""
    pass


class JiraNotFoundError(JiraServiceError):
    """Raised when the project or Jira endpoint cannot be found."""
    pass


class JiraRateLimitError(JiraServiceError):
    """Raised on HTTP 429 Too Many Requests."""
    pass


class JiraNetworkTimeoutError(JiraServiceError):
    """
    Raised when an HTTP connection or read times out.
    WARNING: Blindly retrying ticket creation after a timeout risks duplicate tickets,
    as Jira may have received and created the issue before the client timed out.
    """
    pass


class JiraServerError(JiraServiceError):
    """Raised on Jira Cloud 5xx server errors."""
    pass


# ==============================================================================
# Jira Service Class
# ==============================================================================

class JiraService:
    """Service for interacting with Jira Cloud REST API or returning mock responses."""

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or settings

    def create_mock_issue(self, case_id: str, summary: str) -> Dict[str, str]:
        """
        Simulates ticket creation without contacting any external network.
        Guarantees that no real Jira ticket is created.
        """
        logger.info("Executing mock ticket creation for case_id=%s", case_id)
        mock_id = f"MOCK-{case_id.replace('CASE-', '')}" if "CASE-" in case_id else f"MOCK-001"
        return {
            "id": mock_id,
            "key": mock_id,
            "url": f"https://mock.jira.local/browse/{mock_id}",
            "status": "created_simulated",
        }

    def create_jira_issue(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """
        Creates an issue in Jira Cloud via REST API POST /rest/api/{version}/issue.

        Args:
            payload: Issue payload matching Jira REST API format {"fields": {...}}.

        Returns:
            Dictionary with 'id', 'key', and 'url'.

        Raises:
            JiraConfigurationError, JiraAuthenticationError, JiraValidationError,
            JiraNetworkTimeoutError, JiraRateLimitError, JiraServerError.
        """
        cfg_error = self.config.validate_jira_config()
        if cfg_error:
            raise JiraConfigurationError(cfg_error)

        base_url = self.config.get_clean_jira_base_url()
        api_version = self.config.JIRA_API_VERSION or "3"
        url = f"{base_url}/rest/api/{api_version}/issue"

        # Jira Cloud uses Basic Authentication with email:api_token
        auth_str = f"{self.config.JIRA_EMAIL}:{self.config.JIRA_API_TOKEN}"
        encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

        headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Safe logging without credentials
        logger.info(
            "Sending issue creation request to Jira: %s (Project: %s, IssueType: %s)",
            url,
            self.config.JIRA_PROJECT_KEY,
            self.config.JIRA_ISSUE_TYPE,
        )

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.config.JIRA_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout as exc:
            # IMPORTANT: Do not retry automatically.
            raise JiraNetworkTimeoutError(
                "Jira request timed out. The issue creation request was sent, but no response was "
                "received within the timeout limit. Do NOT retry blindly without checking whether "
                "an issue was already created to avoid creating duplicate tickets."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise JiraServiceError(f"Network error while connecting to Jira: {exc}") from exc

        # Handle HTTP status codes
        if response.status_code == 201:
            data = response.json()
            issue_key = data.get("key", "UNKNOWN")
            issue_id = data.get("id", "UNKNOWN")
            issue_url = f"{base_url}/browse/{issue_key}"
            logger.info("Successfully created Jira issue: %s (%s)", issue_key, issue_url)
            return {
                "id": str(issue_id),
                "key": issue_key,
                "url": issue_url,
                "status": "created",
            }

        self._handle_jira_error_response(response)
        raise JiraServiceError(f"Unexpected Jira response: HTTP {response.status_code}")

    def _handle_jira_error_response(self, response: requests.Response) -> None:
        """Parses Jira error bodies and raises specific, actionable exceptions."""
        status = response.status_code
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}

        # Format Jira error messages if available
        messages = []
        if isinstance(body, dict):
            if "errorMessages" in body and body["errorMessages"]:
                messages.extend(body["errorMessages"])
            if "errors" in body and isinstance(body["errors"], dict):
                for field, err in body["errors"].items():
                    messages.append(f"{field}: {err}")
        err_detail = " | ".join(messages) if messages else response.text

        if status in (401, 403):
            raise JiraAuthenticationError(
                f"Jira authentication failed (HTTP {status}). "
                f"Check that JIRA_EMAIL and JIRA_API_TOKEN are valid and have permission "
                f"to create issues in project '{self.config.JIRA_PROJECT_KEY}'. Details: {err_detail}"
            )

        if status == 404:
            raise JiraNotFoundError(
                f"Jira resource not found (HTTP 404). "
                f"Verify that JIRA_BASE_URL ({self.config.JIRA_BASE_URL}) is correct. Details: {err_detail}"
            )

        if status == 400:
            raise JiraValidationError(
                f"Jira rejected the issue payload (HTTP 400). "
                f"Verify that project '{self.config.JIRA_PROJECT_KEY}' and issue type "
                f"'{self.config.JIRA_ISSUE_TYPE}' exist and allow specified fields. Details: {err_detail}"
            )

        if status == 429:
            raise JiraRateLimitError(
                f"Jira Cloud rate limit exceeded (HTTP 429). Retry after a delay. Details: {err_detail}"
            )

        if 500 <= status < 600:
            raise JiraServerError(
                f"Jira Cloud internal server error (HTTP {status}). Details: {err_detail}"
            )

        raise JiraServiceError(f"Jira API call failed with HTTP {status}: {err_detail}")
