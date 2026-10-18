from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import re
from pathlib import Path
from typing import Any

from validator_eval import RESULTS_DIR, _load_cases, _metrics, run_evaluation

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = ROOT / "eval" / "validator_summary.md"
MODELS = ("openai/gpt-oss-120b", "openai/gpt-oss-20b")
PROMPTS = ("v1", "v2")
REPETITIONS = 3
METRICS = (
    "accuracy",
    "false_approves",
    "false_rejections",
    "failure_type_accuracy",
    "judge_errors",
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _mean_sd(values: list[float]) -> str:
    mean = statistics.mean(values)
    deviation = statistics.stdev(values) if len(values) > 1 else 0.0
    return f"{mean:.3f} ± {deviation:.3f}"


def _summary(reports: dict[tuple[str, str], list[dict[str, Any]]]) -> str:
    lines = [
        "# Validator repeated evaluation summary",
        "",
        f"Dataset: 28 simulated answer/ticket dossiers. Each prompt/model pair was run "
        f"{REPETITIONS} times. Groq was pinned as the only judge provider; no provider "
        "fallback was allowed. Standard deviations are sample standard deviations "
        f"(`n={REPETITIONS}`). Per-case JSON logs are intentionally kept under the ignored "
        "`eval/results/validator_runs/` directory and are not committed.",
        "",
        "| Groq judge model | Prompt | Accuracy (mean ± SD) | False approves (mean ± SD) | False rejections (mean ± SD) | Failure-type accuracy (mean ± SD) | Judge errors (mean ± SD) | Per-run accuracy |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for model in MODELS:
        for prompt in PROMPTS:
            runs = reports[(model, prompt)]
            values = {metric: [run["metrics"][metric] for run in runs] for metric in METRICS}
            per_run = ", ".join(f"{value:.3f}" for value in values["accuracy"])
            lines.append(
                f"| `{model}` | {prompt} | {_mean_sd(values['accuracy'])} "
                f"| {_mean_sd(values['false_approves'])} "
                f"| {_mean_sd(values['false_rejections'])} "
                f"| {_mean_sd(values['failure_type_accuracy'])} "
                f"| {_mean_sd(values['judge_errors'])} | {per_run} |"
            )

    lines.extend(["", "## Pooled confusion counts", ""])
    for model in MODELS:
        for prompt in PROMPTS:
            pooled: dict[str, dict[str, int]] = {}
            for run in reports[(model, prompt)]:
                for expected, actuals in run["metrics"]["confusion_matrix"].items():
                    row = pooled.setdefault(expected, {})
                    for actual, count in actuals.items():
                        row[actual] = row.get(actual, 0) + count
            lines.extend(
                [
                    f"### `{model}` / {prompt}",
                    "",
                    "| Expected \\ Actual | " + " | ".join(pooled) + " |",
                    "|" + "---|" * (len(pooled) + 1),
                ]
            )
            for expected, actuals in pooled.items():
                lines.append(
                    "| " + expected + " | "
                    + " | ".join(str(actuals.get(actual, 0)) for actual in pooled)
                    + " |"
                )
            lines.append("")

    lines.extend(
        [
            "## Interpretation",
            "",
            "These are repeated measurements on one small, hand-authored test set, "
            "not independent estimates of production reliability. The per-run spread "
            "captures observed judge variability on these dossiers only. A zero "
            "false-approve count here does not establish a low real-world false-approve "
            "rate; expand and independently curate the test set before making that claim.",
        ]
    )
    return "\n".join(lines) + "\n"


def _reuse_report(
    output_path: Path,
    model: str,
    prompt: str,
    expected_case_ids: list[str],
) -> dict[str, Any] | None:
    if not output_path.is_file():
        return None
    report = json.loads(output_path.read_text(encoding="utf-8"))
    expected_prompt_hash = hashlib.sha256(
        (ROOT / "prompts" / f"validator_{prompt}.md").read_bytes()
    ).hexdigest()
    if (
        report.get("prompt_version") != prompt
        or report.get("requested_judge_model") != model
        or report.get("prompt_sha256", expected_prompt_hash) != expected_prompt_hash
        or [item.get("case_id") for item in report.get("results", [])] != expected_case_ids
    ):
        return None

    for item in report["results"]:
        if (
            item.get("judge_error") is None
            and item.get("reason") == "LLM judge returned an invalid contract response."
        ):
            item["judge_error"] = "Judge returned an invalid decision schema."
        item["passed"] = (
            item.get("judge_error") is None
            and item["actual_verdict"] == item["expected_verdict"]
            and item["actual_failure_type"] == item["expected_failure_type"]
        )
    report["prompt_sha256"] = report.get(
        "prompt_sha256",
        hashlib.sha256((ROOT / "prompts" / f"validator_{prompt}.md").read_bytes()).hexdigest(),
    )
    report["metrics"] = _metrics(report["results"])
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def run_matrix(
    results_root: Path = RESULTS_DIR / "validator_runs",
    summary_path: Path = DEFAULT_SUMMARY,
    resume: bool = False,
) -> None:
    expected_case_ids = [case["case_id"] for case in _load_cases(ROOT / "eval" / "validator_cases.jsonl")]
    reports: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for model in MODELS:
        for prompt in PROMPTS:
            reports[(model, prompt)] = []
            model_root = results_root / _slug(model)
            for repetition in range(1, REPETITIONS + 1):
                output_dir = model_root / f"run-{repetition}"
                print(
                    f"\n=== model={model} prompt={prompt} "
                    f"repetition={repetition}/{REPETITIONS} ===",
                    flush=True,
                )
                output_path = output_dir / f"validator_{prompt}.json"
                report = _reuse_report(output_path, model, prompt, expected_case_ids) if resume else None
                if report is not None:
                    print(f"Reusing completed report {output_path}", flush=True)
                else:
                    report = run_evaluation(
                        prompt,
                        results_dir=output_dir,
                        groq_model=model,
                    )
                providers_seen = set(report["providers_seen"])
                if (
                    report["requested_judge_model"] != model
                    or providers_seen - {"groq"}
                    or (report["judge_model"] is not None and report["judge_model"] != model)
                ):
                    raise RuntimeError(
                        "Evaluation did not use the requested Groq model: "
                        f"requested={model}, provider={report['judge_provider']}, "
                        f"actual={report['judge_model']}"
                    )
                reports[(model, prompt)].append(report)

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(_summary(reports), encoding="utf-8")
    print(f"\nSummary written to {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repeat v1/v2 Validator evaluations using two pinned Groq judge models."
    )
    parser.add_argument("--results-root", type=Path, default=RESULTS_DIR / "validator_runs")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse completed per-case reports under the selected results root.",
    )
    args = parser.parse_args()
    run_matrix(args.results_root, args.summary, args.resume)


if __name__ == "__main__":
    main()
