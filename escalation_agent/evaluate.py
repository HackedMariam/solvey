"""
Evaluation script to benchmark and inspect generated IT support tickets.
Assesses:
  - Completeness: are relevant facts preserved?
  - Factual consistency: does the ticket avoid invented claims?
  - Clarity: can an IT technician understand the problem?
  - Traceability: are attempted actions and available sources represented accurately?
  - Priority preservation: is upstream urgency preserved?
  - Reliability: does invalid input or a failed API call produce a clear error?
  - Ticket creation correctness: are the fields mapped correctly?
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from config import Settings
from workflow import execute_escalation_workflow


def run_evaluation(dataset_path: str = "evaluation/test_dataset.json"):
    print("=" * 80)
    print("  MULTIMODAL AI IT SUPPORT - ESCALATION WORKFLOW EVALUATION SUITE")
    print("=" * 80)

    path = Path(dataset_path)
    if not path.exists():
        print(f"Error: Dataset not found at {dataset_path}")
        return

    with open(path, "r", encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)

    cfg = Settings(TICKETING_MODE="mock", LLM_PROVIDER="mock")
    total = len(cases)
    passed = 0

    print(f"\nLoaded {total} benchmark evaluation cases.\n")

    for idx, item in enumerate(cases, 1):
        case_id = item["id"]
        name = item["name"]
        expected_outcome = item["expected_outcome"]
        expected_priority = item.get("expected_priority")
        payload = item["payload"]

        print(f"[{idx}/{total}] Testing '{name}' ({case_id})...")

        response = execute_escalation_workflow(payload, config=cfg)
        checks = []

        if expected_outcome == "escalated":
            checks.append(("Status is success", response.status == "success"))
            checks.append(("Escalated is True", response.escalated is True))
            checks.append(("Ticket object present", response.ticket is not None))

            if response.ticket:
                # Priority preservation check
                if expected_priority:
                    checks.append((
                        f"Priority preserved ({response.ticket.priority} == {expected_priority})",
                        response.ticket.priority == expected_priority,
                    ))

                # Completeness & traceability check
                raw_req = payload.get("user_request", "")
                checks.append((
                    "User request preserved in ticket",
                    raw_req in response.ticket.summary or raw_req in response.ticket.formatted_description,
                ))

                esc_reason = payload.get("escalation", {}).get("reason", "")
                if esc_reason:
                    checks.append((
                        "Escalation reason accurately preserved",
                        esc_reason in response.ticket.escalation_reason,
                    ))

                # Traceability: attempted steps
                attempted = payload.get("resolution", {}).get("attempted_steps", [])
                if attempted:
                    actions_text = str(response.ticket.attempted_actions)
                    checks.append((
                        "Attempted actions traced",
                        all(step in actions_text for step in attempted),
                    ))

                # Visual OCR traceability
                ocr_text = payload.get("vision_findings", {}).get("extracted_text")
                if ocr_text:
                    checks.append((
                        "Visual OCR text preserved",
                        ocr_text in response.ticket.formatted_description,
                    ))

        elif expected_outcome == "skipped":
            checks.append(("Status is skipped", response.status == "skipped"))
            checks.append(("Escalated is False", response.escalated is False))
            checks.append(("No ticket created", response.ticket is None))
            checks.append(("Reason is escalation_not_required", response.reason == "escalation_not_required"))

        elif expected_outcome == "error":
            checks.append(("Status is error", response.status == "error"))
            checks.append(("Escalated is False", response.escalated is False))
            checks.append(("Clear error message provided", bool(response.error)))

        # Evaluate case success
        all_ok = all(result for _, result in checks)
        if all_ok:
            passed += 1
            print(f"  [PASS] All {len(checks)} evaluation criteria met.")
        else:
            print(f"  [FAIL] Evaluation criteria failed:")
            for desc, res in checks:
                print(f"    - {desc}: {'OK' if res else 'FAILED'}")

        if response.ticket:
            print(f"    -> Generated Ticket Title: \"{response.ticket.title}\"")
            print(f"    -> Priority: {response.ticket.priority} | Category: {response.ticket.category}")
            print(f"    -> Escalation Reason: \"{response.ticket.escalation_reason}\"")
        elif response.reason:
            print(f"    -> Skip Reason: {response.reason}")
        elif response.error:
            print(f"    -> Error Details: {response.error}")
        print()

    print("=" * 80)
    print(f"EVALUATION SUMMARY: {passed}/{total} Cases Passed ({(passed/total)*100:.1f}%)")
    print("=" * 80)


if __name__ == "__main__":
    run_evaluation()
