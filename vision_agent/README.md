---
title: Solvey Vision Agent
emoji: 🛠️
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 5.50.0
app_file: app.py
pinned: false
---

# Solvey Vision Agent

The intake/vision agent for Solvey. It receives a screenshot and an optional text
description, then returns observation-only JSON for the downstream triage agent.

## What it does

- Reads the screenshot and the user text together.
- Extracts the issue summary, user-reported symptoms, environment, visible text,
  UI elements, technical indicators, missing information, and uncertainties.
- Does **not** diagnose or propose fixes. That belongs to the next agent.
- Returns a no-image-compatible object when only text is provided.

## Files

| Path | Purpose |
|---|---|
| `app.py` | Gradio app for local use and the Hugging Face Space |
| `requirements.txt` | Runtime dependencies for the Space |
| `schema.json` | JSON Schema for the output contract |
| `prompts/system_prompt_v0.md` | Baseline generic screenshot description |
| `prompts/system_prompt_v1.md` | Active intake prompt with output contract |

## Model

- Base: `Qwen/Qwen2.5-VL-3B-Instruct`
- Adapter: `HackedM/solvey-qwen2.5-vl-3b-lora`
- The app uses the adapter by default.

The adapter was trained on the answer format (`Category / Difficulty / Solution`).
It may not follow the intake JSON perfectly. If the output is unstable, test with the
base model by wrapping generation in `with model.disable_adapter():`, or retrain the
adapter on intake JSON targets.

## Deploy on Hugging Face Spaces

1. Create a **Gradio** Space with **ZeroGPU** hardware.
2. Upload `app.py`, `requirements.txt`, and `schema.json`.
3. Keep the Space SDK at **Gradio 5.50.0** (Gradio 6 conflicts with
   `transformers==4.57.1` over `huggingface-hub`).
4. If the adapter repo is private, add `HF_TOKEN` in
   **Settings → Variables and secrets**.
5. Factory rebuild after changing `requirements.txt`.

## Run locally

```bash
pip install -r requirements.txt gradio spaces
export HF_TOKEN=...          # PowerShell: $env:HF_TOKEN="..."
python app.py
```

## Output

The app returns JSON matching `schema.json`:

- `issue_summary`
- `user_reported_symptoms`
- `environment` + `environment_source`
- `visual_summary`
- `visible_text`
- `observed_elements`
- `observed_symptoms`
- `technical_details`
- `missing_information`
- `uncertainties`
- `visual_evidence_confidence`

If the model returns invalid JSON, the app returns a schema-shaped fallback with the
error recorded in `uncertainties`.
