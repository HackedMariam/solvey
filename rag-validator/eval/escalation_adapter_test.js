const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const adapterSource = fs.readFileSync(path.join(root, "n8n", "escalation_agent_adapter.js"), "utf8");
const context = {};
vm.runInNewContext(
  `${adapterSource}\nglobalThis.adapter = { toColleagueInput, toValidatorDossier };`,
  context,
);
const dossier = JSON.parse(fs.readFileSync(path.join(root, "examples", "dossier_ticket.json"), "utf8"));
const colleagueInput = context.adapter.toColleagueInput(dossier);

assert.equal(colleagueInput.case_id, "acct-1842");
assert.equal(colleagueInput.user_request, dossier.user_text);
assert.equal(colleagueInput.triage.category, "Authentication & Access");
assert.equal(colleagueInput.triage.subcategory, "MFA/authentication failure");
assert.equal(colleagueInput.triage.urgency, "critical");
assert.equal(colleagueInput.escalation.required, true);

const converted = context.adapter.toValidatorDossier({
  status: "success",
  case_id: "acct-1842",
  synthesized_ticket: {
    ticket_title: "[Authentication & Access - Account compromise] Unexpected MFA prompt",
    priority_level: "critical",
    summary: "Unexpected MFA approval prompt on a potentially compromised account.",
    formatted_description: "The external agent's formatted draft is deliberately not used.",
    attempted_actions: ["No troubleshooting steps were attempted."],
    escalation_reason: "Possible account compromise.",
  },
}, dossier);

assert.equal(converted.draft_ticket.priority, "critical");
assert.match(converted.draft_ticket.title, /^\[Authentication & Access - .+\] .+/);
for (const heading of [
  "Incident Overview",
  "User Request",
  "Visual Findings & Terminal OCR",
  "Retrieved Technical Documentation (RAG)",
  "Attempted Troubleshooting & Outcomes",
  "Reason for Escalation",
  "Suggested Assignee Group: IT Support (informational only)",
]) {
  assert.ok(converted.draft_ticket.description.includes(heading), `missing ticket section: ${heading}`);
}
assert.ok(converted.draft_ticket.description.includes("Case ID: acct-1842"));
assert.ok(converted.draft_ticket.description.includes("Approve sign-in?"));

const adapterWorkflow = JSON.parse(fs.readFileSync(path.join(root, "n8n", "escalation_agent.json"), "utf8"));
const requestNode = adapterWorkflow.nodes.find((node) => node.name === "Request colleague ticket draft (no Jira)");
assert.equal(requestNode.parameters.url, "={{ $('Escalation Endpoint Config').first().json.format_preview_url }}");
assert.equal(requestNode.parameters.method, "POST");
assert.equal(requestNode.parameters.options.timeout, 30000);
assert.equal(requestNode.onError, "continueErrorOutput");
assert.ok(!adapterWorkflow.nodes.some((node) => node.type.includes("jira")));
const endpointConfig = adapterWorkflow.nodes.find((node) => node.name === "Escalation Endpoint Config");
assert.equal(endpointConfig.parameters.assignments.assignments.length, 1);
assert.equal(endpointConfig.parameters.assignments.assignments[0].name, "format_preview_url");
assert.equal(endpointConfig.parameters.assignments.assignments[0].value, "https://YOUR-ESCALATION-SERVICE/format-preview");
assert.deepEqual(
  adapterWorkflow.connections["Request colleague ticket draft (no Jira)"].main[1].map((target) => target.node),
  ["Prepare local Ticket Agent fallback"],
);
assert.equal(
  adapterWorkflow.connections["Prepare local Ticket Agent fallback"].main[0][0].node,
  "Call local Ticket Agent fallback",
);
assert.equal(
  adapterWorkflow.nodes.find((node) => node.name === "Call local Ticket Agent fallback").parameters.workflowId.cachedResultName,
  "Ticket Agent",
);

const mainWorkflow = JSON.parse(fs.readFileSync(path.join(root, "n8n", "solvey_main.json"), "utf8"));
for (const name of ["Call Colleague Escalation Agent", "Regenerate Ticket Once with Colleague Agent"]) {
  const call = mainWorkflow.nodes.find((node) => node.name === name);
  assert.ok(call, `missing Execute Workflow node: ${name}`);
  assert.equal(call.parameters.workflowId.cachedResultName, "Colleague Escalation Agent adapter (draft only)");
  assert.equal(
    mainWorkflow.connections[name].main[0][0].node,
    name === "Call Colleague Escalation Agent" ? "Call Validator (ticket)" : "Call Validator (ticket retry)",
  );
}

console.log("Escalation adapter conversion, timeout fallback, and Validator routing passed.");
console.log(JSON.stringify(converted));
