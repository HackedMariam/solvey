from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
N8N = ROOT / "n8n"
ADAPTER_PATH = N8N / "escalation_agent.json"
MAIN_PATH = N8N / "solvey_main.json"
ADAPTER_SOURCE = N8N / "escalation_agent_adapter.js"


def node_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://solvey.local/escalation-adapter/{name}"))


def code_node(name: str, position: list[int], js_code: str) -> dict:
    return {
        "parameters": {"mode": "runOnceForAllItems", "jsCode": js_code},
        "id": node_id(name),
        "name": name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": position,
    }


def main() -> None:
    source = ADAPTER_SOURCE.read_text(encoding="utf-8").rstrip()
    endpoint_config = {
        "parameters": {
            "assignments": {
                "assignments": [
                    {
                        "id": node_id("format-preview-url"),
                        "name": "format_preview_url",
                        "value": "https://YOUR-ESCALATION-SERVICE/format-preview",
                        "type": "string",
                    }
                ]
            },
            "includeOtherFields": False,
            "options": {},
        },
        "id": node_id("Escalation Endpoint Config"),
        "name": "Escalation Endpoint Config",
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.5,
        "position": [420, 300],
    }
    prepare = code_node(
        "Prepare colleague escalation input",
        [640, 300],
        source
        + "\nconst dossier=$('Execute Workflow Trigger').first().json; return [{json:{dossier,colleague_input:toColleagueInput(dossier)}}];",
    )
    request = {
        "parameters": {
            "method": "POST",
            "url": "={{ $('Escalation Endpoint Config').first().json.format_preview_url }}",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.colleague_input }}",
            "options": {"timeout": 30000},
        },
        "id": node_id("Request colleague ticket draft"),
        "name": "Request colleague ticket draft (no Jira)",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [920, 300],
        "onError": "continueErrorOutput",
    }
    convert = code_node(
        "Convert generated ticket to Validator dossier",
        [1200, 220],
        source
        + "\nconst response=$input.first().json; const original=$('Prepare colleague escalation input').first().json.dossier;"
        + "\nreturn [{json:toValidatorDossier(response,original)}];",
    )
    fallback_input = code_node(
        "Prepare local Ticket Agent fallback",
        [1200, 440],
        "const dossier=$('Prepare colleague escalation input').first().json.dossier;"
        + "\nreturn [{json:dossier}];",
    )
    local_fallback = {
        "parameters": {
            "workflowId": {
                "__rl": True,
                "value": "RESELECT_AFTER_IMPORT",
                "mode": "list",
                "cachedResultName": "Ticket Agent",
            },
            "workflowInputs": {"mappingMode": "passthrough"},
            "options": {"waitForSubWorkflow": True},
        },
        "id": node_id("Call local Ticket Agent fallback"),
        "name": "Call local Ticket Agent fallback",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.2,
        "position": [1460, 440],
        "onError": "stopWorkflow",
    }
    workflow = {
        "name": "Colleague Escalation Agent adapter (draft only)",
        "nodes": [
            {
                "parameters": {"inputSource": "passthrough"},
                "id": node_id("Execute Workflow Trigger"),
                "name": "Execute Workflow Trigger",
                "type": "n8n-nodes-base.executeWorkflowTrigger",
                "typeVersion": 1.1,
                "position": [240, 300],
            },
            endpoint_config,
            prepare,
            request,
            convert,
            fallback_input,
            local_fallback,
        ],
        "connections": {
            "Execute Workflow Trigger": {"main": [[{"node": "Escalation Endpoint Config", "type": "main", "index": 0}]]},
            "Escalation Endpoint Config": {"main": [[{"node": "Prepare colleague escalation input", "type": "main", "index": 0}]]},
            "Prepare colleague escalation input": {"main": [[{"node": "Request colleague ticket draft (no Jira)", "type": "main", "index": 0}]]},
            "Request colleague ticket draft (no Jira)": {
                "main": [
                    [{"node": "Convert generated ticket to Validator dossier", "type": "main", "index": 0}],
                    [{"node": "Prepare local Ticket Agent fallback", "type": "main", "index": 0}],
                ]
            },
            "Prepare local Ticket Agent fallback": {"main": [[{"node": "Call local Ticket Agent fallback", "type": "main", "index": 0}]]},
        },
        "active": False,
        "settings": {"executionOrder": "v1"},
        "versionId": node_id("version"),
        "meta": {"templateCredsSetupCompleted": False},
        "tags": [],
    }
    ADAPTER_PATH.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    main_workflow = json.loads(MAIN_PATH.read_text(encoding="utf-8"))
    name_map = {
        "Call Ticket Agent": "Call Colleague Escalation Agent",
        "Regenerate Ticket Once": "Regenerate Ticket Once with Colleague Agent",
    }
    for node in main_workflow["nodes"]:
        if node["name"] not in name_map:
            continue
        old_name = node["name"]
        new_name = name_map[old_name]
        node["name"] = new_name
        node["parameters"]["workflowId"]["value"] = "RESELECT_AFTER_IMPORT"
        node["parameters"]["workflowId"]["cachedResultName"] = "Colleague Escalation Agent adapter (draft only)"
        main_workflow["connections"][new_name] = main_workflow["connections"].pop(old_name)
        for branches in main_workflow["connections"].values():
            for output in branches.get("main", []):
                for target in output:
                    if target["node"] == old_name:
                        target["node"] = new_name
    MAIN_PATH.write_text(json.dumps(main_workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Built colleague adapter with 30-second local Ticket Agent fallback for draft and regeneration calls.")


if __name__ == "__main__":
    main()
