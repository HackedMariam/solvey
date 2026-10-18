from __future__ import annotations

import shutil
import subprocess
import json
from pathlib import Path

import pytest

from src.validator.service import validate_dossier

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required to test n8n Code-node behavior")
def test_colleague_escalation_adapter_conversion_and_workflow_routing():
    result = subprocess.run(
        ["node", str(ROOT / "eval" / "escalation_adapter_test.js")],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Escalation adapter conversion, timeout fallback, and Validator routing passed." in result.stdout
    converted_dossier = json.loads(result.stdout.splitlines()[-1])
    decision = validate_dossier(converted_dossier, judge=_ApproveJudge())
    assert decision["verdict"] == "approve"


class _ApproveJudge:
    provider = "test"

    def judge(self, dossier, prompt_version="v2"):
        return {
            "verdict": "approve",
            "failure_type": None,
            "target_stage": None,
            "feedback_for_stage": "",
            "reason": "The adapter output satisfies the ticket contract.",
        }
