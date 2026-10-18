"""
Unit tests for Jira Service and API interaction mocking.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests

from config import Settings
from jira_service import (
    JiraAuthenticationError,
    JiraConfigurationError,
    JiraNetworkTimeoutError,
    JiraNotFoundError,
    JiraRateLimitError,
    JiraServerError,
    JiraService,
    JiraValidationError,
)


@pytest.fixture
def mock_jira_settings() -> Settings:
    return Settings(
        TICKETING_MODE="jira",
        JIRA_BASE_URL="https://company.atlassian.net",
        JIRA_EMAIL="it-agent@company.com",
        JIRA_API_TOKEN="mock-token-xyz-123456",
        JIRA_PROJECT_KEY="IT",
        JIRA_ISSUE_TYPE="Task",
        JIRA_API_VERSION="3",
        JIRA_TIMEOUT_SECONDS=5,
    )


def test_create_mock_issue():
    """Mock issue creation must return simulated ID without making network calls."""
    service = JiraService()
    res = service.create_mock_issue("CASE-999", "Test summary")
    assert res["id"] == "MOCK-999"
    assert "https://mock.jira.local/browse/MOCK-999" in res["url"]
    assert res["status"] == "created_simulated"


def test_jira_creation_success(mock_jira_settings):
    """Test successful 201 response from Jira Cloud REST API."""
    service = JiraService(mock_jira_settings)
    mock_payload = {"fields": {"summary": "Test issue"}}

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "10050",
            "key": "IT-42",
            "self": "https://company.atlassian.net/rest/api/3/issue/10050",
        }
        mock_post.return_value = mock_response

        result = service.create_jira_issue(mock_payload)
        assert result["id"] == "10050"
        assert result["key"] == "IT-42"
        assert result["url"] == "https://company.atlassian.net/browse/IT-42"
        assert result["status"] == "created"


def test_jira_authentication_failure(mock_jira_settings):
    """Test 401 Unauthorized raises JiraAuthenticationError."""
    service = JiraService(mock_jira_settings)
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"errorMessages": ["Unauthorized user."]}
        mock_post.return_value = mock_response

        with pytest.raises(JiraAuthenticationError) as exc:
            service.create_jira_issue({"fields": {}})
        assert "Jira authentication failed" in str(exc.value)


def test_jira_validation_failure_bad_project(mock_jira_settings):
    """Test 400 Bad Request raises JiraValidationError with field details."""
    service = JiraService(mock_jira_settings)
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "errorMessages": [],
            "errors": {"project": "Project 'INVALID' does not exist."},
        }
        mock_post.return_value = mock_response

        with pytest.raises(JiraValidationError) as exc:
            service.create_jira_issue({"fields": {}})
        assert "Project 'INVALID' does not exist." in str(exc.value)


def test_jira_network_timeout_handling(mock_jira_settings):
    """Test that a request timeout raises JiraNetworkTimeoutError and warns against blind retries."""
    service = JiraService(mock_jira_settings)
    with patch("requests.post", side_effect=requests.exceptions.Timeout("Connection timed out")):
        with pytest.raises(JiraNetworkTimeoutError) as exc:
            service.create_jira_issue({"fields": {}})
        assert "Do NOT retry blindly" in str(exc.value)


def test_jira_missing_configuration_raises_error():
    """In jira mode without credentials, JiraConfigurationError must be raised."""
    incomplete_settings = Settings(
        TICKETING_MODE="jira",
        JIRA_BASE_URL=None,  # Missing
        JIRA_EMAIL=None,
    )
    service = JiraService(incomplete_settings)
    with pytest.raises(JiraConfigurationError) as exc:
        service.create_jira_issue({"fields": {}})
    assert "Missing required Jira configuration variables" in str(exc.value)
