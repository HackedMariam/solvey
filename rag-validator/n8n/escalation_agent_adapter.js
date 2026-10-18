const CATEGORY_LABELS = {
  network_vpn: "Network & VPN",
  auth_access: "Authentication & Access",
  email_communication: "Email & Communication",
  software_apps: "Software & Applications",
  system_os: "System & OS",
  general: "General",
  other: "Other / out of scope",
};
const SUBCATEGORY_LABELS = {
  vpn_auth_failure: "VPN authentication failure",
  vpn_connection_failure: "VPN connection failure",
  wifi_connectivity: "Wi-Fi connectivity issue",
  dns_network_config: "DNS/network configuration error",
  internet_connection: "Internet connection problem",
  wrong_expired_password: "Wrong/expired password",
  account_locked: "Account locked",
  mfa_failure: "MFA/authentication failure",
  permission_denied: "Permission denied",
  restricted_resource_access: "Access to restricted resource",
  cannot_send_email: "Cannot send email",
  cannot_receive_email: "Cannot receive email",
  email_auth_failure: "Email authentication failure",
  mailbox_full: "Mailbox/storage full",
  email_client_config: "Email client configuration problem",
  app_wont_launch: "Application won't launch",
  app_crash: "Application crash",
  installation_failure: "Installation failure",
  app_config_error: "Application configuration error",
  software_update_failure: "Software update failure",
  system_error: "Windows/system error",
  driver_problem: "Driver problem",
  os_update_failure: "OS update failure",
  performance_issue: "System performance issue",
  hardware_error: "Hardware-related error",
  out_of_scope: "Out of scope",
};

function toColleagueInput(dossier) {
  if (!dossier || dossier.mode !== "ticket") throw new Error("Escalation adapter requires a ticket-mode dossier");
  const vision = dossier.vision;
  const triage = dossier.triage || {};
  const retrieval = dossier.retrieval || {};
  const observations = Array.isArray(vision?.observations) ? vision.observations : [];
  const steps = Array.isArray(dossier.attempted_actions)
    ? dossier.attempted_actions
    : Array.isArray(dossier.resolution?.attempted_steps) ? dossier.resolution.attempted_steps : [];
  return {
    case_id: String(dossier.request_id || ""),
    user_request: String(dossier.user_text || ""),
    vision_findings: vision ? {
      observations,
      extracted_text: [vision.error_text, vision.error_code].filter((value) => typeof value === "string" && value).join("\n") || null,
      confidence: typeof vision.confidence === "number" ? vision.confidence : null,
    } : null,
    triage: {
      category: CATEGORY_LABELS[triage.category] || "Other / out of scope",
      subcategory: SUBCATEGORY_LABELS[triage.subcategory] || "Out of scope",
      urgency: ["low", "medium", "high", "critical"].includes(triage.urgency) ? triage.urgency : "medium",
      confidence: typeof triage.confidence === "number" ? triage.confidence : null,
    },
    rag: {
      status: Array.isArray(retrieval.chunks) && retrieval.chunks.length ? "documents_found" : "no_documents_found",
      document_count: Array.isArray(retrieval.chunks) ? retrieval.chunks.length : 0,
      sources: (retrieval.chunks || []).map((chunk) => [chunk.title, chunk.source].filter(Boolean).join(" — ")),
      findings: (retrieval.chunks || []).map((chunk) => chunk.text || chunk.table_raw || "").filter(Boolean),
    },
    resolution: {
      status: steps.length ? "failed" : null,
      attempted_steps: steps.map((step) => typeof step === "string" ? step : `${step.step || step.action || "Action"} (Status: ${step.status || "reported"})`),
      user_feedback: dossier.user_feedback || dossier.resolution?.user_feedback || null,
    },
    escalation: {
      required: true,
      reason: String(dossier.ticket_reason || dossier.feedback_for_stage || "Escalation requested by the support workflow."),
    },
  };
}

function toValidatorDossier(response, original) {
  if (!response || response.status !== "success" || !response.synthesized_ticket) {
    throw new Error(`Escalation agent did not return a ticket draft (status=${response?.status || "missing"})`);
  }
  const ticket = response.synthesized_ticket;
  const triage = original.triage || {};
  const categoryLabel = CATEGORY_LABELS[triage.category] || "Other / out of scope";
  const priority = ["low", "medium", "high", "critical"].includes(triage.urgency) ? triage.urgency : "medium";
  const ticketSummary = String(ticket.summary || ticket.ticket_title || "Escalated support incident").trim();
  const generatedTitle = String(ticket.ticket_title || "").trim();
  const title = generatedTitle.startsWith(`[${categoryLabel} - `) && generatedTitle.includes("] ")
    ? generatedTitle
    : `[${categoryLabel} - ${(generatedTitle || triage.problem_type || "Support incident").slice(0, 64)}] ${ticketSummary}`;
  const vision = original.vision;
  const retrievalChunks = Array.isArray(original.retrieval?.chunks) ? original.retrieval.chunks : [];
  const attempted = Array.isArray(ticket.attempted_actions) && ticket.attempted_actions.length
    ? ticket.attempted_actions
    : Array.isArray(original.attempted_actions) ? original.attempted_actions : [];
  const attempts = attempted.length
    ? attempted.map((step) => typeof step === "string" ? step : `${step.step || step.action || "Action"} (Status: ${step.status || "reported"})`).join("\n")
    : "No troubleshooting steps were reported.";
  const userFeedback = original.user_feedback || original.resolution?.user_feedback || "Not provided.";
  const visualText = typeof vision?.error_text === "string" && vision.error_text
    ? vision.error_text
    : "Not provided.";
  const sources = retrievalChunks.length
    ? retrievalChunks.map((chunk, index) => {
      const provenance = [chunk.title || `Source ${index + 1}`, chunk.source, chunk.url].filter(Boolean).join(" — ");
      return `${provenance}\nKey passage: ${chunk.table_raw || chunk.text || "No passage text provided."}`;
    }).join("\n\n")
    : "No technical documentation was retrieved.";
  const rationale = String(ticket.escalation_reason || original.ticket_reason || "Human review was requested.");
  const description = [
    "Incident Overview",
    `Case ID: ${String(original.request_id || response.case_id || "unknown")}`,
    `Category: ${categoryLabel}`,
    `Preserved Urgency (Priority): ${priority}`,
    `Summary: ${ticketSummary}`,
    "",
    "User Request",
    String(original.user_text || "Not provided."),
    "",
    "Visual Findings & Terminal OCR",
    `Application: ${vision?.application || "Not visible"}`,
    `Observations: ${(vision?.observations || []).join("; ") || "None reported."}`,
    "Exact error text:",
    "```",
    visualText,
    "```",
    "",
    "Retrieved Technical Documentation (RAG)",
    `Sources and key passages:\n${sources}`,
    "",
    "Attempted Troubleshooting & Outcomes",
    attempts,
    `User reported feedback: ${userFeedback}`,
    "",
    "Reason for Escalation",
    rationale,
    "",
    "Suggested Assignee Group: IT Support (informational only)",
  ].join("\n");
  return {
    ...original,
    request_id: String(original.request_id || response.case_id || ""),
    draft_ticket: { title, description, priority },
  };
}
