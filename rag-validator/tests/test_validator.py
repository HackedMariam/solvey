from __future__ import annotations

import json
from pathlib import Path

from src.validator.service import validate_dossier
from eval.validator_eval import _load_cases

ROOT = Path(__file__).resolve().parents[1]


class ApproveJudge:
    provider = "fake"

    def judge(self, dossier, prompt_version="v2"):
        assert dossier["mode"] in {"answer", "ticket"}
        assert prompt_version in {"v1", "v2"}
        return {
            "verdict": "approve",
            "failure_type": None,
            "target_stage": None,
            "feedback_for_stage": "",
            "reason": "The dossier is coherent and grounded.",
        }


def _answer_dossier() -> dict:
    return json.loads((ROOT / "examples" / "dossier_answer.json").read_text(encoding="utf-8"))


def _ticket_dossier() -> dict:
    return json.loads((ROOT / "examples" / "dossier_ticket.json").read_text(encoding="utf-8"))


def test_complete_answer_dossier_reaches_judge_and_approves():
    result = validate_dossier(_answer_dossier(), judge=ApproveJudge())

    assert result["verdict"] == "approve"
    assert result["failure_type"] is None
    assert result["stage_checks"]["retrieval"]["status"] == "ok"


def test_missing_dossier_field_escalates_with_exact_field_path():
    dossier = _answer_dossier()
    del dossier["triage"]["search_query"]

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "escalate"
    assert result["failure_type"] == "inconsistent_pipeline"
    assert "triage.search_query" in result["feedback_for_stage"]


def test_missing_vision_error_text_is_a_precise_pipeline_error():
    dossier = _answer_dossier()
    del dossier["vision"]["error_text"]

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["failure_type"] == "inconsistent_pipeline"
    assert result["target_stage"] == "vision"
    assert "vision.error_text" in result["reason"]


def test_low_retrieval_relevance_retries_without_calling_judge():
    dossier = _answer_dossier()
    dossier["retrieval"]["chunks"][0]["score"] = 0.47
    dossier["retrieval"]["chunks"][1]["score"] = 0.4

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "retry_retrieval"
    assert result["failure_type"] == "insufficient_evidence"
    assert "not an answer refusal" in result["reason"]


def test_retrieval_retry_limit_escalates():
    dossier = _answer_dossier()
    dossier["retrieval"]["chunks"] = []
    dossier["attempt_counts"] = {"retry_retrieval": 1, "regenerate": 0, "total": 1}

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "escalate"
    assert result["failure_type"] == "insufficient_evidence"


def test_sensitive_keyword_repairs_missing_flag_then_escalates_answer():
    dossier = _answer_dossier()
    dossier["user_text"] = "My work account was hacked and someone logged in."
    dossier["triage"].pop("is_sensitive")

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "escalate"
    assert result["failure_type"] == "safety_risk"
    assert result["sanitized_dossier"]["triage"]["is_sensitive"] is True
    assert result["sanitized_dossier"]["triage"]["urgency"] == "high"
    assert result["stage_checks"]["triage"]["corrections"]


def test_known_subcategory_repairs_mismatched_category():
    dossier = _answer_dossier()
    dossier["triage"]["category"] = "auth_access"

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "approve"
    assert result["sanitized_dossier"]["triage"]["category"] == "network_vpn"
    assert result["stage_checks"]["triage"]["corrections"]


def test_command_must_match_cited_passage_verbatim():
    dossier = _answer_dossier()
    dossier["draft_answer"]["steps"][0]["command"] = "ipconfig /flushdns /all"
    dossier["retrieval"]["chunks"][0]["text"] = "Run `ipconfig /flushdns` to clear DNS."
    dossier["retrieval"]["chunks"][1]["text"] = "Use `ipconfig /flushdns` to clear the resolver cache."

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "regenerate"
    assert result["failure_type"] == "unfaithful_answer"


def test_destructive_command_escalates_before_llm():
    dossier = _answer_dossier()
    dossier["draft_answer"]["steps"][0]["command"] = "rm -rf /"

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "escalate"
    assert result["failure_type"] == "safety_risk"


def test_invalid_source_ids_request_regeneration():
    dossier = _answer_dossier()
    dossier["draft_answer"]["steps"][0]["source_ids"] = ["S99"]

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "regenerate"
    assert result["failure_type"] == "unfaithful_answer"


def test_ticket_secrets_are_redacted_and_reported():
    dossier = _ticket_dossier()
    dossier["draft_ticket"]["summary"] += " Password: SuperSecret777!"

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "regenerate"
    assert result["failure_type"] == "leak"
    assert "SuperSecret777!" not in result["sanitized_dossier"]["draft_ticket"]["summary"]
    assert "[REDACTED]" in result["sanitized_dossier"]["draft_ticket"]["summary"]


def test_ticket_missing_required_field_regenerates_once():
    dossier = _ticket_dossier()
    del dossier["draft_ticket"]["evidence"]

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "regenerate"
    assert result["failure_type"] == "incomplete_ticket"
    assert "evidence" in result["feedback_for_stage"]


def test_ticket_sensitive_incident_can_be_validated_before_creation():
    result = validate_dossier(_ticket_dossier(), judge=ApproveJudge())

    assert result["verdict"] == "approve"
    assert result["failure_type"] is None
    assert result["sanitized_dossier"]["draft_ticket"]["priority"] == "critical"


def test_final_message_personal_data_is_redacted_and_regenerated():
    dossier = _answer_dossier()
    dossier["draft_answer"]["final_message"] += " Contact me at user@example.edu."

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "regenerate"
    assert result["failure_type"] == "leak"
    assert "user@example.edu" not in result["sanitized_dossier"]["draft_answer"]["final_message"]
    assert "[REDACTED]" in result["sanitized_dossier"]["draft_answer"]["final_message"]


def test_leak_after_regeneration_limit_escalates():
    dossier = _ticket_dossier()
    dossier["draft_ticket"]["summary"] += " Password: SuperSecret777!"
    dossier["attempt_counts"] = {"retry_retrieval": 0, "regenerate": 1, "total": 1}

    result = validate_dossier(dossier, judge=ApproveJudge())

    assert result["verdict"] == "escalate"
    assert result["failure_type"] == "leak"
    assert "SuperSecret777!" not in result["sanitized_dossier"]["draft_ticket"]["summary"]


def test_malformed_unhashable_fields_escalate_instead_of_crashing():
    malformed_dossiers = []

    dossier = _answer_dossier()
    dossier["mode"] = []
    malformed_dossiers.append(dossier)

    dossier = _answer_dossier()
    dossier["triage"]["urgency"] = []
    malformed_dossiers.append(dossier)

    dossier = _answer_dossier()
    dossier["triage"]["language"] = []
    malformed_dossiers.append(dossier)

    dossier = _answer_dossier()
    dossier["vision"]["observations"] = [{}]
    malformed_dossiers.append(dossier)

    dossier = _ticket_dossier()
    dossier["draft_ticket"]["priority"] = []
    malformed_dossiers.append(dossier)

    for dossier in malformed_dossiers:
        result = validate_dossier(dossier, judge=ApproveJudge())
        assert result["verdict"] == "escalate"
        assert result["failure_type"] == "inconsistent_pipeline"


def test_hard_case_overlays_resolve_to_complete_dossiers():
    cases = _load_cases(ROOT / "eval" / "validator_cases.jsonl")

    assert len(cases) == 28
    masked_password = next(
        case for case in cases if case["case_id"] == "ticket-partially-masked-password"
    )
    assert masked_password["dossier"]["draft_ticket"]["summary"].startswith(
        "The user entered password: Pa****word42"
    )
    injection = next(case for case in cases if case["case_id"] == "ocr-hidden-prompt-injection")
    assert injection["dossier"]["vision"]["observations"][0].startswith("Tiny extracted text")


def test_malformed_judge_enums_escalate_without_crashing():
    class MalformedJudge:
        provider = "fake"

        def judge(self, _dossier, prompt_version="v2"):
            assert _dossier["mode"] == "answer"
            assert prompt_version in {"v1", "v2"}
            return {
                "verdict": ["approve"],
                "failure_type": [],
                "target_stage": None,
                "feedback_for_stage": "",
                "reason": "malformed enum values",
            }

    result = validate_dossier(_answer_dossier(), judge=MalformedJudge())

    assert result["verdict"] == "escalate"
    assert result["failure_type"] == "inconsistent_pipeline"
