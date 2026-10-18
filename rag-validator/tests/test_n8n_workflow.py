from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from eval.validator_node_parity import run_node_parity

WORKFLOW_PATH = Path(__file__).resolve().parents[1] / "n8n" / "rag_retrieve.json"


def test_rag_retrieve_workflow_has_importable_retrieval_path():
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    nodes = {node["name"]: node for node in workflow["nodes"]}

    assert workflow["active"] is False
    assert set(nodes) == {
        "Execute Workflow Trigger",
        "OpenAI Query Embedding",
        "Qdrant Search (category)",
        "Need Unfiltered Fallback?",
        "Qdrant Search (fallback)",
        "Format S1-S5 Response",
    }
    assert nodes["Execute Workflow Trigger"]["type"] == "n8n-nodes-base.executeWorkflowTrigger"
    embedding = nodes["OpenAI Query Embedding"]["parameters"]
    assert embedding["url"] == "https://api.openai.com/v1/embeddings"
    assert "text-embedding-3-small" in embedding["jsonBody"]
    assert "dimensions: 1536" in embedding["jsonBody"]

    filtered = nodes["Qdrant Search (category)"]["parameters"]
    fallback = nodes["Qdrant Search (fallback)"]["parameters"]
    assert "/collections/it_kb_blocks/points/query" in filtered["url"]
    assert "score_threshold: 0.3" in filtered["jsonBody"]
    assert "key: 'category'" in filtered["jsonBody"]
    assert "score_threshold: 0.3" in fallback["jsonBody"]
    assert "filter:" not in fallback["jsonBody"]

    connections = workflow["connections"]
    assert connections["Need Unfiltered Fallback?"]["main"][0][0]["node"] == "Qdrant Search (fallback)"
    assert connections["Need Unfiltered Fallback?"]["main"][1][0]["node"] == "Format S1-S5 Response"
    assert nodes["Format S1-S5 Response"]["parameters"]["jsCode"].count("S${index + 1}") == 1


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for n8n Code-node parity")
def test_n8n_validator_matches_python_on_validator_cases():
    results = run_node_parity()

    assert len(results) >= 16
