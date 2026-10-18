const VALID_VERDICTS = new Set(["approve", "retry_retrieval", "regenerate", "clarify", "escalate"]);
const VALID_FAILURES = new Set([
  "insufficient_evidence", "unfaithful_answer", "missing_user_info", "safety_risk",
  "inconsistent_pipeline", "incomplete_ticket", "leak",
]);

function response(verdict, failure, target, checks, feedback, reason, dossier, provider) {
  const result = {
    verdict, failure_type: failure, target_stage: target, stage_checks: checks,
    feedback_for_stage: feedback, reason, sanitized_dossier: dossier,
  };
  if (provider) result.judge_provider = provider;
  return result;
}

function finalizeJudge(context, judgment, provider) {
  const { dossier, stage_checks: checks } = context;
  if (!judgment || typeof judgment !== "object") {
    return response("escalate", "inconsistent_pipeline", "validator", checks,
      "The judge response did not match the Validator output schema.", "LLM judge returned an invalid contract response.", dossier, provider);
  }
  let { verdict, failure_type: failure, target_stage: target, feedback_for_stage: feedback = "", reason = "" } = judgment;
  if (!VALID_VERDICTS.has(verdict) || !(VALID_FAILURES.has(failure) || (verdict === "approve" && failure === null))
      || (target !== null && typeof target !== "string") || typeof reason !== "string") {
    return response("escalate", "inconsistent_pipeline", "validator", checks,
      "The judge response did not match the Validator output schema.", "LLM judge returned an invalid contract response.", dossier, provider);
  }
  if (verdict === "approve") {
    failure = null; target = null; feedback = "";
  }
  if (failure === "safety_risk") {
    verdict = "escalate"; target = "ticket";
  } else if (failure === "inconsistent_pipeline") verdict = "escalate";
  else if (failure === "leak") {
    const counts = dossier.attempt_counts;
    if (counts.regenerate < 1 && counts.total < 2) {
      verdict = "regenerate";
      target = dossier.mode === "ticket" ? "ticket" : "answer";
    } else {
      verdict = "escalate";
      target = "ticket";
      feedback = "The allowed regeneration has already been used; escalate for human review.";
      reason += " Regeneration limit reached.";
    }
  } else if (failure === "incomplete_ticket" && dossier.mode === "ticket") {
    if (dossier.attempt_counts.regenerate < 1 && dossier.attempt_counts.total < 2) {
      verdict = "regenerate"; target = "ticket";
    } else { verdict = "escalate"; target = "ticket"; }
  } else if (failure === "insufficient_evidence") {
    if (dossier.attempt_counts.retry_retrieval < 1 && dossier.attempt_counts.total < 2) {
      verdict = "retry_retrieval"; target = "retrieval";
    } else { verdict = "escalate"; target = "ticket"; }
  } else if (failure === "unfaithful_answer") {
    if (dossier.attempt_counts.regenerate < 1 && dossier.attempt_counts.total < 2) {
      verdict = "regenerate"; target = dossier.mode === "answer" ? "answer" : "ticket";
    } else { verdict = "escalate"; target = "ticket"; }
  } else if (failure === "missing_user_info") {
    verdict = "clarify"; target = "user";
  }
  return response(verdict, failure, target, checks, typeof feedback === "string" ? feedback : "", reason, dossier, provider);
}
