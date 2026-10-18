from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.validator.service import JudgeClient, validate_dossier

CASES_PATH = ROOT / "eval" / "validator_cases.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
VERDICTS = ("approve", "retry_retrieval", "regenerate", "clarify", "escalate")


def _load_cases(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            required = {"case_id", "expected_verdict", "expected_failure_type"}
            has_dossier = isinstance(case, dict) and (
                isinstance(case.get("dossier"), dict)
                or isinstance(case.get("dossier_from"), str)
            )
            if not isinstance(case, dict) or not required <= case.keys() or not has_dossier:
                raise ValueError(
                    f"Case at {path}:{line_number} needs {sorted(required)} and a dossier or dossier_from"
                )
            entries.append(case)

    templates = {
        case["case_id"]: case["dossier"]
        for case in entries
        if isinstance(case.get("dossier"), dict)
    }

    def merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    cases: list[dict[str, Any]] = []
    for case in entries:
        if "dossier" not in case and isinstance(case.get("dossier_from"), str):
            template_id = case["dossier_from"]
            if template_id not in templates:
                raise ValueError(f"Case {case['case_id']} references unknown dossier {template_id!r}")
            case["dossier"] = merge(templates[template_id], case.get("overrides", {}))
        cases.append(case)
    if len(cases) < 16:
        raise ValueError(f"Expected at least 16 validator cases; found {len(cases)}")
    return cases


def _metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    confusion: dict[str, dict[str, int]] = {
        expected: {actual: 0 for actual in VERDICTS}
        for expected in VERDICTS
    }
    correct = 0
    false_approves = 0
    false_rejections = 0
    exact_failure_matches = 0
    judge_errors = 0
    for item in results:
        expected = item["expected_verdict"]
        actual = item["actual_verdict"]
        if expected not in VERDICTS or actual not in VERDICTS:
            raise ValueError(f"Unexpected verdict in evaluation: expected={expected} actual={actual}")
        confusion[expected][actual] += 1
        correct += expected == actual
        false_approves += expected != "approve" and actual == "approve"
        false_rejections += expected == "approve" and actual != "approve"
        exact_failure_matches += item["expected_failure_type"] == item["actual_failure_type"]
        judge_errors += item.get("judge_error") is not None
    total = len(results)
    return {
        "cases": total,
        "accuracy": correct / total if total else 0.0,
        "false_approves": false_approves,
        "false_rejections": false_rejections,
        "failure_type_accuracy": exact_failure_matches / total if total else 0.0,
        "judge_errors": judge_errors,
        "confusion_matrix": confusion,
    }


def run_evaluation(
    prompt_version: str,
    cases_path: Path = CASES_PATH,
    results_dir: Path = RESULTS_DIR,
    groq_model: str = "openai/gpt-oss-120b",
) -> dict[str, Any]:
    cases = _load_cases(cases_path)
    judge = JudgeClient(groq_model=groq_model, strict_provider="groq")
    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        judge_error = None
        try:
            actual = validate_dossier(case["dossier"], judge=judge, prompt_version=prompt_version)
        except RuntimeError as exc:
            if not str(exc).startswith("All Validator judge providers failed:"):
                raise
            judge_error = f"{type(exc).__name__}: {exc}"
            actual = {
                "verdict": "escalate",
                "failure_type": "inconsistent_pipeline",
                "target_stage": "validator",
                "reason": "Judge call failed; evaluation records a fail-closed escalation.",
                "judge_provider": None,
            }
        if actual["reason"] == "LLM judge returned an invalid contract response.":
            judge_error = "Judge returned an invalid decision schema."
        result = {
            "case_id": case["case_id"],
            "expected_verdict": case["expected_verdict"],
            "expected_failure_type": case["expected_failure_type"],
            "actual_verdict": actual["verdict"],
            "actual_failure_type": actual["failure_type"],
            "target_stage": actual["target_stage"],
            "reason": actual["reason"],
            "judge_provider": actual.get("judge_provider"),
            "judge_error": judge_error,
            "passed": (
                judge_error is None
                and actual["verdict"] == case["expected_verdict"]
                and actual["failure_type"] == case["expected_failure_type"]
            ),
        }
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"[{index:02d}/{len(cases)}] {case['case_id']}: {status}; "
            f"expected={result['expected_verdict']}/{result['expected_failure_type']}, "
            f"actual={result['actual_verdict']}/{result['actual_failure_type']}",
            flush=True,
        )

    providers = sorted({item["judge_provider"] for item in results if item["judge_provider"]})
    model = judge.model
    report = {
        "prompt_version": prompt_version,
        "prompt_sha256": hashlib.sha256(
            (ROOT / "prompts" / f"validator_{prompt_version}.md").read_bytes()
        ).hexdigest(),
        "judge_model": model,
        "requested_judge_model": groq_model,
        "judge_provider": judge.provider,
        "requested_judge_model": groq_model,
        "providers_seen": providers,
        "metrics": _metrics(results),
        "results": results,
    }
    if prompt_version == "v2":
        baseline_path = results_dir / "validator_v1.json"
        if baseline_path.is_file():
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            if model is not None and baseline.get("judge_model") not in {None, model}:
                raise RuntimeError(
                    "v1/v2 judge models differ; refusing an apples-to-oranges comparison "
                    f"({baseline.get('judge_model')} vs {model})"
                )
    results_dir.mkdir(parents=True, exist_ok=True)
    output_path = results_dir / f"validator_{prompt_version}.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\nJudge: {judge.provider} / {model}")
    print(json.dumps(report["metrics"], indent=2, ensure_ascii=False))
    failures = [item for item in results if not item["passed"]]
    print("\nMisclassified cases:")
    if not failures:
        print("None")
    else:
        for item in failures:
            print(
                f"- {item['case_id']}: expected {item['expected_verdict']}/"
                f"{item['expected_failure_type']}, got {item['actual_verdict']}/"
                f"{item['actual_failure_type']} — {item['reason']}"
            )
    print(f"\nDetailed results: {output_path}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Validator prompts against simulated dossiers.")
    parser.add_argument("--prompt-version", choices=("v1", "v2"), required=True)
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--groq-model", default="openai/gpt-oss-120b")
    args = parser.parse_args()
    run_evaluation(args.prompt_version, args.cases, args.results_dir, args.groq_model)


if __name__ == "__main__":
    main()
