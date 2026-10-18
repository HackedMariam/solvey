from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from eval.validator_eval import CASES_PATH, _load_cases
from src.validator.service import validate_dossier

ROOT = Path(__file__).resolve().parents[1]
NODE_RUNNER = ROOT / "eval" / "validator_node_parity.js"


class _FixtureJudge:
    provider = "parity-test"

    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case

    def judge(self, _dossier: dict[str, Any], prompt_version: str = "v2") -> dict[str, Any]:
        assert prompt_version == "v2"
        expected_verdict = self.case["expected_verdict"]
        return {
            "verdict": expected_verdict,
            "failure_type": self.case["expected_failure_type"],
            "target_stage": {
                "approve": None,
                "retry_retrieval": "retrieval",
                "regenerate": "ticket" if self.case["dossier"]["mode"] == "ticket" else "answer",
                "clarify": "user",
                "escalate": "ticket",
            }[expected_verdict],
            "feedback_for_stage": "parity fixture",
            "reason": "parity fixture",
        }


def run_node_parity(cases_path: Path = CASES_PATH) -> list[dict[str, Any]]:
    cases = _load_cases(cases_path)
    completed = subprocess.run(
        ["node", str(NODE_RUNNER)],
        input=json.dumps(cases, ensure_ascii=False),
        capture_output=True,
        check=True,
        text=True,
        cwd=ROOT,
    )
    node_results = json.loads(completed.stdout)
    python_results = []
    for case in cases:
        result = validate_dossier(case["dossier"], judge=_FixtureJudge(case), prompt_version="v2")
        python_results.append({
            "case_id": case["case_id"],
            "verdict": result["verdict"],
            "failure_type": result["failure_type"],
        })
    by_id = {result["case_id"]: result for result in python_results}
    mismatches = []
    for node_result in node_results:
        python_result = by_id[node_result["case_id"]]
        if (node_result["verdict"], node_result["failure_type"]) != (
            python_result["verdict"], python_result["failure_type"]
        ):
            mismatches.append({"node": node_result, "python": python_result})
    if mismatches:
        raise AssertionError(f"Node/Python Validator parity failed: {json.dumps(mismatches, ensure_ascii=False)}")
    return node_results


if __name__ == "__main__":
    results = run_node_parity()
    print(f"Validator parity passed for {len(results)} cases (Node.js Code-node logic vs Python).")
