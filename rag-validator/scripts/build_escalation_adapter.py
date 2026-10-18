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
    prepare = code_node(
        "Prepare colleague escalation input",
        [480, 300],
        source
        + "\nconst dossier=$input.first().json; return [{json:{dossier,colleague_input:toColleagueInput(dossier)}}];",
    )
    request = {
        "parameters": {
            "method": "POST",
            "url": "https://YOUR-ESCALATION-SERVICE/format-preview",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.colleague_input }}",
            "options": {"timeout": 120000},
        },
        "id": node_id("Request colleague ticket draft"),
        "name": "Request colleague ticket draft (no Jira)",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [740, 300],
        "onError": "stopWorkflow",
    }
    convert = code_node(
        "Convert generated ticket to Validator dossier",
        [1000, 300],
        source
        + "\nconst response=$input.first().json; const original=$('Prepare colleague escalation input').first().json.dossier;"
        + "\nreturn [{json:toValidatorDossier(response,original)}];",
    )
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
            prepare,
            request,
            convert,
        ],
        "connections": {
            "Execute Workflow Trigger": {"main": [[{"node": "Prepare colleague escalation input", "type": "main", "index": 0}]]},
            "Prepare colleague escalation input": {"main": [[{"node": "Request colleague ticket draft (no Jira)", "type": "main", "index": 0}]]},
            "Request colleague ticket draft (no Jira)": {"main": [[{"node": "Convert generated ticket to Validator dossier", "type": "main", "index": 0}]]},
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
    print("Built colleague adapter and routed both primary and one-shot ticket regeneration through it.")


if __name__ == "__main__":
    main()
