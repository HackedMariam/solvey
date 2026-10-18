from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from .service import JudgeClient, validate_dossier

app = FastAPI(title="IT Support Final Validator", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/validate")
def validate(payload: dict[str, Any]) -> dict[str, Any]:
    return validate_dossier(payload, judge=JudgeClient(), prompt_version="v2")
