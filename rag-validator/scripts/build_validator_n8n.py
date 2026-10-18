from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "n8n" / "validator.json"
LOGIC_PATH = ROOT / "n8n" / "validator_logic.js"
DECISION_PATH = ROOT / "n8n" / "validator_decision.js"


def node_id(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://solvey.local/validator/{label}"))


def base_node(name: str, node_type: str, version: float, position: list[int], parameters: dict) -> dict:
    return {
        "parameters": parameters,
        "id": node_id(name),
        "name": name,
        "type": node_type,
        "typeVersion": version,
        "position": position,
    }


def code_node(name: str, position: list[int], js_code: str) -> dict:
    return base_node(
        name,
        "n8n-nodes-base.code",
        2,
        position,
        {"mode": "runOnceForAllItems", "jsCode": js_code},
    )


def if_node(name: str, position: list[int], expression: str) -> dict:
    return base_node(
        name,
        "n8n-nodes-base.if",
        2.2,
        position,
        {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 2,
                },
                "conditions": [
                    {
                        "id": node_id(f"{name}/condition"),
                        "leftValue": expression,
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
    )


def http_node(name: str, position: list[int], url: str, body: str, credential_name: str) -> dict:
    return {
        **base_node(
            name,
            "n8n-nodes-base.httpRequest",
            4.2,
            position,
            {
                "method": "POST",
                "url": url,
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": body,
                "options": {"timeout": 60000},
            },
        ),
        "onError": "continueErrorOutput",
        "credentials": {
            "httpHeaderAuth": {
                "id": "RESELECT_CREDENTIAL",
                "name": credential_name,
            }
        },
    }


def parse_node(name: str, position: list[int], provider: str, expression: str, model_path: str) -> dict:
    code = f"""const response=$input.first().json;
const ctx=$('Deterministic Validator Checks').first().json;
let content=null;
try {{ content={expression}; }} catch (_error) {{ content=null; }}
let judgment=null, ok=false;
if(typeof content==='string') {{
  const cleaned=content.trim().replace(/^```(?:json)?\\\\s*/i,'').replace(/\\\\s*```$/,'');
  try {{ const parsed=JSON.parse(cleaned); if(parsed&&typeof parsed==='object'&&!Array.isArray(parsed)) {{ judgment=parsed; ok=true; }} }} catch (_error) {{ }}
}}
let model=null;
try {{ model={model_path}; }} catch (_error) {{ }}
return [{{json:{{ok,judgment,provider:'{provider}',model,context:ctx.context}}}}];"""
    return code_node(name, position, code)


def main() -> None:
    logic = LOGIC_PATH.read_text(encoding="utf-8").rstrip()
    decision = DECISION_PATH.read_text(encoding="utf-8").rstrip()
    nodes = [
        base_node("Complete Dossier Trigger", "n8n-nodes-base.executeWorkflowTrigger", 1.1, [240, 420], {"inputSource": "passthrough"}),
        code_node("Deterministic Validator Checks", [500, 420], logic + "\nreturn [{json:runDeterministic($input.first().json)}];"),
        if_node("Needs LLM Judge?", [760, 420], "={{ $json.complete !== true }}"),
        code_node("Return Deterministic Verdict", [1020, 640], "return [{json:$input.first().json.result}];"),
        http_node(
            "Groq Judge",
            [1020, 260],
            "https://api.groq.com/openai/v1/chat/completions",
            "={{ JSON.stringify({model:'openai/gpt-oss-120b',temperature:0,max_completion_tokens:1400,messages:[{role:'system',content:$('Deterministic Validator Checks').first().json.judge_request.system},{role:'user',content:$('Deterministic Validator Checks').first().json.judge_request.user}]}) }}",
            "Groq API",
        ),
        parse_node("Parse Groq Judge", [1260, 260], "Groq", "response.choices?.[0]?.message?.content", "response.model"),
        if_node("Groq Judge Valid?", [1500, 260], "={{ $json.ok === true }}"),
        http_node(
            "Gemini Judge Fallback",
            [1740, 420],
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
            "={{ JSON.stringify({systemInstruction:{parts:[{text:$('Deterministic Validator Checks').first().json.judge_request.system}]},contents:[{role:'user',parts:[{text:$('Deterministic Validator Checks').first().json.judge_request.user}]}],generationConfig:{temperature:0,maxOutputTokens:1400,responseMimeType:'application/json'}}) }}",
            "Google Gemini API key",
        ),
        parse_node("Parse Gemini Judge", [1980, 420], "Gemini", "response.candidates?.[0]?.content?.parts?.map(part=>part.text||'').join('')", "'gemini-3.8-flash'"),
        if_node("Gemini Judge Valid?", [2220, 420], "={{ $json.ok === true }}"),
        http_node(
            "OpenAI Judge Fallback",
            [2460, 580],
            "https://api.openai.com/v1/chat/completions",
            "={{ JSON.stringify({model:'gpt-4o-mini',temperature:0,max_tokens:1400,response_format:{type:'json_object'},messages:[{role:'system',content:$('Deterministic Validator Checks').first().json.judge_request.system},{role:'user',content:$('Deterministic Validator Checks').first().json.judge_request.user}]}) }}",
            "OpenAI Validator API",
        ),
        parse_node("Parse OpenAI Judge", [2700, 580], "OpenAI", "response.choices?.[0]?.message?.content", "response.model"),
        if_node("OpenAI Judge Valid?", [2940, 580], "={{ $json.ok === true }}"),
        code_node("Apply Judge Decision", [3180, 280], decision + "\nconst item=$input.first().json; const context=$('Deterministic Validator Checks').first().json.context; return [{json:finalizeJudge(context,item.judgment,item.provider)}];"),
        code_node(
            "All Judges Failed - Escalate",
            [3180, 680],
            """const context=$('Deterministic Validator Checks').first().json.context;
const checks=context.stage_checks;
checks.validator.status='failed';
checks.validator.issues.push('Groq, Gemini and OpenAI judge calls all failed or returned invalid JSON.');
return [{json:{verdict:'escalate',failure_type:'inconsistent_pipeline',target_stage:'validator',stage_checks:checks,
feedback_for_stage:'The Validator could not obtain a valid judge result; route to human review.',
reason:'All configured n8n LLM judge providers failed. No ticket or user answer was approved.',
sanitized_dossier:context.dossier,judge_provider:null}}];""",
        ),
    ]
    names = {node["name"] for node in nodes}
    if len(names) != len(nodes):
        raise ValueError("Workflow node names must be unique")

    def edge(target: str, index: int = 0) -> dict:
        return {"node": target, "type": "main", "index": index}

    connections = {
        "Complete Dossier Trigger": {"main": [[edge("Deterministic Validator Checks")]]},
        "Deterministic Validator Checks": {"main": [[edge("Needs LLM Judge?")]]},
        "Needs LLM Judge?": {"main": [[edge("Groq Judge")], [edge("Return Deterministic Verdict")]]},
        "Groq Judge": {"main": [[edge("Parse Groq Judge")], [edge("Parse Groq Judge")]]},
        "Parse Groq Judge": {"main": [[edge("Groq Judge Valid?")]]},
        "Groq Judge Valid?": {"main": [[edge("Apply Judge Decision")], [edge("Gemini Judge Fallback")]]},
        "Gemini Judge Fallback": {"main": [[edge("Parse Gemini Judge")], [edge("Parse Gemini Judge")]]},
        "Parse Gemini Judge": {"main": [[edge("Gemini Judge Valid?")]]},
        "Gemini Judge Valid?": {"main": [[edge("Apply Judge Decision")], [edge("OpenAI Judge Fallback")]]},
        "OpenAI Judge Fallback": {"main": [[edge("Parse OpenAI Judge")], [edge("Parse OpenAI Judge")]]},
        "Parse OpenAI Judge": {"main": [[edge("OpenAI Judge Valid?")]]},
        "OpenAI Judge Valid?": {"main": [[edge("Apply Judge Decision")], [edge("All Judges Failed - Escalate")]]},
    }
    workflow = {
        "name": "Final Validator - self-contained n8n",
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "versionId": node_id("version"),
        "meta": {"templateCredsSetupCompleted": False},
        "tags": [],
    }
    WORKFLOW_PATH.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built {WORKFLOW_PATH.relative_to(ROOT)} with embedded deterministic checks and three native HTTP providers.")


if __name__ == "__main__":
    main()
