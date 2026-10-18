const TICKET_LABELS = {
  network_vpn: "Network & VPN",
  auth_access: "Authentication & Access",
  email_communication: "Email & Communication",
  software_apps: "Software & Applications",
  system_os: "System & OS",
  general: "General",
  other: "Other / out of scope",
};
const REQUIRED_TICKET_SECTIONS = [
  "Incident Overview",
  "User Request",
  "Visual Findings & Terminal OCR",
  "Retrieved Technical Documentation (RAG)",
  "Attempted Troubleshooting & Outcomes",
  "Reason for Escalation",
  "Suggested Assignee Group: IT Support",
];
const SECRET_PATTERNS = [
  /\b(password|passwd|pwd|secret|api[_ -]?key|access[_ -]?token|client[_ -]?secret)\b\s*[:=]\s*(?!\[REDACTED\])([^\s,;]+)/i,
  /\b(?:sk-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,})\b/,
  /\bBearer\s+[A-Za-z0-9._~+/=-]{12,}/i,
];

function normalizeLabel(value) {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function overviewValue(overview, label) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = overview.match(new RegExp(`(?:^|[\\n(,]\\s*)${escaped}\\s*:\\s*([^,)\\r\\n]+)`, "i"));
  return match ? match[1].trim() : null;
}

function hasSecret(description) {
  return SECRET_PATTERNS.some((pattern) => pattern.test(description));
}

function validateCompleteTicket(dossier) {
  if (!dossier || dossier.mode !== "ticket" || !dossier.triage || !dossier.draft_ticket) return false;
  const ticket = dossier.draft_ticket;
  if (typeof ticket.title !== "string" || typeof ticket.description !== "string"
      || !ticket.title.trim() || !ticket.description.trim() || hasSecret(ticket.description)) return false;
  const label = TICKET_LABELS[dossier.triage.category];
  if (!label || ticket.priority !== dossier.triage.urgency
      || !["low", "medium", "high", "critical"].includes(ticket.priority)) return false;

  const titlePrefix = ticket.title.match(/^\[([^\]]+?)\s*-\s*/);
  if (!titlePrefix || normalizeLabel(titlePrefix[1]) !== normalizeLabel(label)
      || !ticket.title.includes("] ")) return false;
  if (titlePrefix[1] !== label) {
    ticket.title = ticket.title.replace(/^\[[^\]]+?\s*-\s*/, `[${label} - `);
  }

  const description = ticket.description;
  const positions = REQUIRED_TICKET_SECTIONS.map((section) => description.indexOf(section));
  if (positions.some((position) => position < 0)
      || positions.some((position, index) => index > 0 && position <= positions[index - 1])) return false;
  if (typeof dossier.request_id !== "string" || !dossier.request_id.trim()) return false;
  const overview = description.slice(0, positions[1]);
  const caseId = overviewValue(overview, "Case ID");
  const category = overviewValue(overview, "Category");
  const urgency = overviewValue(overview, "Preserved Urgency (Priority)");
  const summary = overviewValue(overview, "Summary");
  if (caseId !== dossier.request_id || !category
      || normalizeLabel(category) !== normalizeLabel(label)
      || urgency !== dossier.triage.urgency || !summary) return false;

  const reasonStart = positions[5] + REQUIRED_TICKET_SECTIONS[5].length;
  const reason = description.slice(reasonStart, positions[6]).replace(/^[\s:：-]+/, "").trim();
  return reason.length > 0;
}

function addClarificationToSensitiveTicket(dossier, question) {
  const description = dossier.draft_ticket.description;
  if (/Clarification requested:/i.test(description)) return true;
  const text = typeof question === "string" && question.trim()
    ? question.trim()
    : "Please provide the missing details needed for investigation.";
  const heading = /(^|\n)(User Request:?[^\r\n]*)(\r?\n)/i;
  if (!heading.test(description)) return false;
  dossier.draft_ticket.description = description.replace(
    heading,
    (_match, start, line, newline) => `${start}${line}${newline}Clarification requested: ${text}\n`,
  );
  return true;
}

function processDeterministicTicketResult(result) {
  if (!result || typeof result !== "object" || !result.sanitized_dossier) return result;
  const dossier = result.sanitized_dossier;
  if (dossier.mode !== "ticket") return result;

  if (result.failure_type === "missing_user_info"
      && result.verdict === "clarify"
      && dossier.triage?.is_sensitive === true
      && addClarificationToSensitiveTicket(dossier, result.feedback_for_stage || dossier.triage.clarification_question)
      && validateCompleteTicket(dossier)) {
    result.verdict = "approve";
    result.failure_type = null;
    result.target_stage = null;
    result.feedback_for_stage = "";
    result.reason = "The missing-information question is recorded in the sensitive-incident ticket; escalation is not blocked.";
    result.sanitized_dossier = dossier;
    return result;
  }

  if (result.failure_type === "incomplete_ticket"
      && validateCompleteTicket(dossier)) {
    result.verdict = "approve";
    result.failure_type = null;
    result.target_stage = null;
    result.feedback_for_stage = "";
    result.reason = "All required ticket sections and a non-empty escalation reason are present; deterministic ticket and safety checks passed.";
    if (result.stage_checks?.ticket) {
      result.stage_checks.ticket.status = "ok";
      result.stage_checks.ticket.issues = result.stage_checks.ticket.issues.filter(
        (entry) => !/title must use|Incident Overview is missing|required section missing/i.test(entry),
      );
      result.stage_checks.ticket.corrections.push("complete ticket approved after checking the required sections and escalation reason");
    }
    result.sanitized_dossier = dossier;
  }
  return result;
}
