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

function ticketHasRequiredSectionsAndReason(dossier) {
  const sections = [
    "Incident Overview", "User Request", "Visual Findings & Terminal OCR",
    "Retrieved Technical Documentation (RAG)", "Attempted Troubleshooting & Outcomes",
    "Reason for Escalation", "Suggested Assignee Group: IT Support",
  ];
  if (dossier.mode !== "ticket" || typeof dossier.draft_ticket?.description !== "string") return false;
  const description = dossier.draft_ticket.description;
  const positions = sections.map((section) => description.indexOf(section));
  if (positions.some((position) => position < 0)
      || positions.some((position, index) => index > 0 && position <= positions[index - 1])) return false;
  return description.slice(positions[5] + sections[5].length, positions[6])
    .replace(/^[\s:：-]+/, "").trim().length > 0;
}

function addTicketClarification(dossier, question, checks) {
  const ticket = dossier.draft_ticket;
  if (!ticket || typeof ticket.description !== "string") return false;
  if (/Clarification requested:/i.test(ticket.description)) return true;
  const text = typeof question === "string" && question.trim()
    ? question.trim()
    : "Please provide the missing details needed for investigation.";
  const heading = /(^|\n)(User Request:?[^\r\n]*)(\r?\n)/i;
  if (!heading.test(ticket.description)) return false;
  ticket.description = ticket.description.replace(
    heading,
    (_match, start, line, newline) => `${start}${line}${newline}Clarification requested: ${text}\n`,
  );
  if (checks.ticket) {
    checks.ticket.corrections.push("missing-information question added to the sensitive-incident ticket");
  }
  return true;
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
  } else if (dossier.mode === "ticket" && ticketHasRequiredSectionsAndReason(dossier)
      && failure === "incomplete_ticket") {
    verdict = "approve";
    failure = null;
    target = null;
    feedback = "";
    reason = "All required ticket sections and a non-empty escalation reason are present; deterministic ticket and safety checks passed.";
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
    if (dossier.mode === "ticket" && dossier.triage?.is_sensitive
        && ticketHasRequiredSectionsAndReason(dossier)) {
      addTicketClarification(dossier, feedback || dossier.triage.clarification_question, checks);
      if (/Clarification requested:/i.test(dossier.draft_ticket.description)) {
        verdict = "approve";
        failure = null;
        target = null;
        feedback = "";
        reason = "The missing-information question is recorded in the sensitive-incident ticket; escalation is not blocked.";
      } else {
        verdict = "escalate";
        target = "ticket";
      }
    } else {
      verdict = "clarify"; target = "user";
    }
  }
  return response(verdict, failure, target, checks, typeof feedback === "string" ? feedback : "", reason, dossier, provider);
}
