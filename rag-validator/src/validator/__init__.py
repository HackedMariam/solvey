"""End-to-end quality gate for answer and escalation-ticket dossiers."""

from .service import validate_dossier

__all__ = ["validate_dossier"]
