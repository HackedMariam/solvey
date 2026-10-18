from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from pathlib import Path
from types import ModuleType


@lru_cache(maxsize=1)
def load_guardrails() -> ModuleType:
    configured_path = os.getenv("IT_SUPPORT_GUARDRAILS_PATH")
    default_path = (
        Path(__file__).resolve().parents[3]
        / "it-support-langgraph"
        / "itsupport"
        / "guardrails.py"
    )
    path = Path(configured_path) if configured_path else default_path
    if not path.is_file():
        raise FileNotFoundError(
            "Shared guardrails.py was not found. Set IT_SUPPORT_GUARDRAILS_PATH "
            f"to its location; checked {path}"
        )

    spec = importlib.util.spec_from_file_location("it_support_shared_guardrails", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load shared guardrails module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
