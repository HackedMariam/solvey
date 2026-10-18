const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const logic = fs.readFileSync(path.join(root, "n8n", "validator_logic.js"), "utf8");
const decision = fs.readFileSync(path.join(root, "n8n", "validator_decision.js"), "utf8");
const deterministicReturn = fs.readFileSync(path.join(root, "n8n", "validator_deterministic_return.js"), "utf8");
const run = new Function("dossier", `${logic}\nreturn runDeterministic(dossier);`);
const finish = new Function("context", "judgment", `${decision}\nreturn finalizeJudge(context, judgment, "test");`);
const returnNode = new Function("result", `${deterministicReturn}\nreturn processDeterministicTicketResult(result);`);
const base = JSON.parse(fs.readFileSync(path.join(root, "examples", "dossier_ticket.json"), "utf8"));

function capturedTicket() {
  const dossier = structuredClone(base);
  dossier.request_id = "test-3";
  dossier.user_text = "I clicked a link in a phishing email. My corporate Microsoft 365 email account (Outlook) is compromised.";
  Object.assign(dossier.triage, {
    category: "email_communication",
    subcategory: "email_auth_failure",
    urgency: "critical",
    is_sensitive: true,
    sensitivity_reason: "The user reports a phishing email and a compromised account.",
    needs_clarification: false,
    clarification_question: "Which email address was affected?",
  });
  dossier.draft_ticket = {
    title: "[Email Communication - Account Compromised] Corporate Microsoft 365 email account compromised",
    description: [
      "Incident Overview (Case ID: test-3, Category: Email Communication, Preserved Urgency (Priority): critical, Summary: Corporate Microsoft 365 email account compromised)",
      "",
      "User Request:",
      "The user clicked a link in a phishing email.",
      "",
      "Visual Findings & Terminal OCR:",
      "Not provided",
      "",
      "Retrieved Technical Documentation (RAG):",
      "None retrieved",
      "",
      "Attempted Troubleshooting & Outcomes:",
      "No troubleshooting steps have been attempted yet.",
      "",
      "Reason for Escalation:",
      "The corporate email account is reported compromised after a phishing link was clicked.",
      "",
      "Suggested Assignee Group: IT Support (informational only)",
    ].join("\n"),
    priority: "critical",
  };
  return dossier;
}

const incompleteTicketDossier = capturedTicket();
const checkedCompleteTicket = run(incompleteTicketDossier);
assert.equal(checkedCompleteTicket.complete, false, JSON.stringify(checkedCompleteTicket.result));
const incompleteTicketOverride = finish(checkedCompleteTicket.context, {
  verdict: "regenerate",
  failure_type: "incomplete_ticket",
  target_stage: "ticket",
  feedback_for_stage: "Complete the ticket.",
  reason: "False incomplete-ticket judgment.",
});
assert.equal(incompleteTicketOverride.verdict, "approve");
assert.equal(incompleteTicketOverride.failure_type, null);
assert.ok(incompleteTicketOverride.sanitized_dossier.draft_ticket.title.startsWith("[Email & Communication - "));
const oldDeterministicResult = returnNode({
  verdict: "escalate",
  failure_type: "incomplete_ticket",
  target_stage: "ticket",
  feedback_for_stage: "Regeneration limit reached.",
  reason: "Ticket regeneration limit reached.",
  stage_checks: { ticket: { status: "failed", issues: ["title must use required category label"], corrections: [] } },
  sanitized_dossier: capturedTicket(),
});
assert.equal(oldDeterministicResult.verdict, "approve");
assert.equal(oldDeterministicResult.failure_type, null);
assert.ok(oldDeterministicResult.sanitized_dossier.draft_ticket.title.startsWith("[Email & Communication - "));

const clarificationDossier = capturedTicket();
clarificationDossier.triage.needs_clarification = true;
const checkedClarification = run(clarificationDossier);
assert.equal(checkedClarification.complete, false, JSON.stringify(checkedClarification.result));
assert.match(checkedClarification.context.dossier.draft_ticket.description, /Clarification requested: Which email address was affected\?/);
const clarificationOverride = finish(checkedClarification.context, {
  verdict: "clarify",
  failure_type: "missing_user_info",
  target_stage: "user",
  feedback_for_stage: "Which email address was affected?",
  reason: "A human should collect the missing detail.",
});
assert.equal(clarificationOverride.verdict, "approve");
assert.equal(clarificationOverride.failure_type, null);
assert.match(clarificationOverride.sanitized_dossier.draft_ticket.description, /Clarification requested: Which email address was affected\?/);
const oldClarificationResult = returnNode({
  verdict: "clarify",
  failure_type: "missing_user_info",
  target_stage: "user",
  feedback_for_stage: "Which email address was affected?",
  reason: "Triage requested clarification.",
  stage_checks: { ticket: { status: "ok", issues: [], corrections: [] } },
  sanitized_dossier: clarificationDossier,
});
assert.equal(oldClarificationResult.verdict, "approve");
assert.match(oldClarificationResult.sanitized_dossier.draft_ticket.description, /Clarification requested: Which email address was affected\?/);

const noReason = capturedTicket();
noReason.draft_ticket.description = noReason.draft_ticket.description.replace(
  "The corporate email account is reported compromised after a phishing link was clicked.",
  "",
);
const noReasonResult = run(noReason);
assert.equal(noReasonResult.complete, true);
assert.equal(noReasonResult.result.verdict, "regenerate");
assert.equal(noReasonResult.result.failure_type, "incomplete_ticket");

const secretTicket = capturedTicket();
secretTicket.draft_ticket.description += "\nPassword: DoNotExpose123!";
const secretResult = run(secretTicket);
assert.equal(secretResult.complete, true);
assert.equal(secretResult.result.failure_type, "leak");
assert.ok(!secretResult.result.sanitized_dossier.draft_ticket.description.includes("DoNotExpose123!"));
const oldLeakingResult = returnNode({
  verdict: "regenerate",
  failure_type: "leak",
  target_stage: "ticket",
  feedback_for_stage: "Secret was redacted.",
  reason: "Secret redaction is required.",
  stage_checks: { ticket: { status: "failed", issues: ["secret detected"], corrections: [] } },
  sanitized_dossier: secretResult.result.sanitized_dossier,
});
assert.equal(oldLeakingResult.verdict, "regenerate");
assert.equal(oldLeakingResult.failure_type, "leak");

console.log("Native ticket Validator regressions passed.");
