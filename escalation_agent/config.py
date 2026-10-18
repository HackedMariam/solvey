"""
Configuration module for the Escalation and Jira Ticket-Creation Workflow.
Loads environment variables safely and provides structured application settings.
"""

from enum import Enum
import os
from typing import Dict, Optional
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file if available
load_dotenv()


class TicketingMode(str, Enum):
    MOCK = "mock"
    JIRA = "jira"


class LLMProvider(str, Enum):
    MOCK = "mock"
    OPENAI = "openai"
    GEMINI = "gemini"
    CUSTOM = "custom"


# Standard mapping from upstream triage urgency (low, medium, high, critical)
# to Jira default priority levels (Low, Medium, High, Highest)
DEFAULT_PRIORITY_MAPPING: Dict[str, str] = {
    "critical": "Highest",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}


class Settings(BaseSettings):
    """Application settings with environment variable support and safe defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General Workflow Mode
    TICKETING_MODE: str = Field(default=TicketingMode.MOCK.value)

    # LLM Settings
    LLM_PROVIDER: str = Field(default=LLMProvider.MOCK.value)
    LLM_MODEL: str = Field(default="gpt-4o-mini")
    LLM_API_KEY: Optional[str] = Field(default=None)
    LLM_BASE_URL: Optional[str] = Field(default=None)
    LLM_TIMEOUT_SECONDS: int = Field(default=30)
    LLM_FALLBACK_ON_FAILURE: bool = Field(default=True)

    # Jira Settings
    JIRA_BASE_URL: Optional[str] = Field(default=None)
    JIRA_EMAIL: Optional[str] = Field(default=None)
    JIRA_API_TOKEN: Optional[str] = Field(default=None)
    JIRA_PROJECT_KEY: Optional[str] = Field(default=None)
    JIRA_ISSUE_TYPE: str = Field(default="Task")
    JIRA_API_VERSION: str = Field(default="3")
    JIRA_TIMEOUT_SECONDS: int = Field(default=15)

    # Server Settings
    PORT: int = Field(default=8000)
    HOST: str = Field(default="0.0.0.0")
    DEBUG: bool = Field(default=False)

    def is_mock_mode(self) -> bool:
        """Return True if running in mock ticketing mode."""
        return self.TICKETING_MODE.lower().strip() == TicketingMode.MOCK.value

    def is_jira_mode(self) -> bool:
        """Return True if running in real Jira ticketing mode."""
        return self.TICKETING_MODE.lower().strip() == TicketingMode.JIRA.value

    def get_clean_jira_base_url(self) -> Optional[str]:
        """Return sanitized Jira base URL (scheme + domain only), stripping any board/project paths."""
        if not self.JIRA_BASE_URL:
            return None
        from urllib.parse import urlparse
        parsed = urlparse(self.JIRA_BASE_URL.strip())
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return self.JIRA_BASE_URL.strip().rstrip("/")

    def get_jira_credentials(self) -> Dict[str, Optional[str]]:
        """Return Jira connection details."""
        return {
            "base_url": self.get_clean_jira_base_url(),
            "email": self.JIRA_EMAIL,
            "api_token": self.JIRA_API_TOKEN,
            "project_key": self.JIRA_PROJECT_KEY,
            "issue_type": self.JIRA_ISSUE_TYPE,
            "api_version": self.JIRA_API_VERSION,
        }

    def validate_jira_config(self) -> Optional[str]:
        """Validate Jira configuration when in Jira mode. Returns error message if invalid."""
        if not self.is_jira_mode():
            return None

        missing = []
        if not self.JIRA_BASE_URL:
            missing.append("JIRA_BASE_URL")
        if not self.JIRA_EMAIL:
            missing.append("JIRA_EMAIL")
        if not self.JIRA_API_TOKEN:
            missing.append("JIRA_API_TOKEN")
        if not self.JIRA_PROJECT_KEY:
            missing.append("JIRA_PROJECT_KEY")

        if missing:
            return (
                f"Missing required Jira configuration variables: {', '.join(missing)}. "
                "Please configure them in your .env file or environment, or set TICKETING_MODE=mock."
            )
        return None

    def safe_dict(self) -> dict:
        """Return a dictionary of settings with secrets masked for safe logging."""
        raw = self.model_dump()
        masked = {}
        for k, v in raw.items():
            if ("KEY" in k or "TOKEN" in k or "PASSWORD" in k) and v:
                masked[k] = f"{v[:3]}...{v[-3:]}" if len(str(v)) > 6 else "***"
            else:
                masked[k] = v
        return masked


# Global settings instance
settings = Settings()
