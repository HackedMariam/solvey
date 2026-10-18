const fs = require("node:fs");
const path = require("node:path");

const base = path.resolve(__dirname, "..", "n8n");
const logic = fs.readFileSync(path.join(base, "validator_logic.js"), "utf8");
const decision = fs.readFileSync(path.join(base, "validator_decision.js"), "utf8");
const run = new Function("dossier", `${logic}\nreturn runDeterministic(dossier);`);
const finish = new Function("context", "judgment", `${decision}\nreturn finalizeJudge(context, judgment, "parity-test");`);
const cases = JSON.parse(fs.readFileSync(0, "utf8"));

const results = cases.map((testCase) => {
  const checked = run(testCase.dossier);
  if (checked.complete) {
    return {
      case_id: testCase.case_id,
      verdict: checked.result.verdict,
      failure_type: checked.result.failure_type,
    };
  }
  const judgeVerdict = testCase.judge_verdict || testCase.expected_verdict;
  const judgeFailure = Object.hasOwn(testCase, "judge_failure_type")
    ? testCase.judge_failure_type
    : testCase.expected_failure_type;
  const target = {
    retry_retrieval: "retrieval",
    regenerate: testCase.dossier.mode === "ticket" ? "ticket" : "answer",
    clarify: "user",
    escalate: "ticket",
    approve: null,
  }[judgeVerdict];
  const result = finish(checked.context, {
    verdict: judgeVerdict,
    failure_type: judgeFailure,
    target_stage: target,
    feedback_for_stage: "parity fixture",
    reason: "parity fixture",
  });
  return { case_id: testCase.case_id, verdict: result.verdict, failure_type: result.failure_type };
});

process.stdout.write(JSON.stringify(results));
