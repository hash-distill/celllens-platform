"""Versioned, local prompt assets for the read-only research assistant."""

import hashlib
import json
from pathlib import Path

PROMPT_VERSION = "1.0.2"
_ROOT = Path(__file__).parent
_TASKS = ("interpret", "coverage", "next_steps", "figure", "genes", "metabolism", "comparison")
_FILES = ("role.md", "evidence.md", "teaching.md", "review.md", "expression_chart.md") + tuple(
    f"tasks/{name}.md" for name in _TASKS
)
# Load a fixed allowlist at startup. User text never selects a filesystem path.
_TEXT = {name: (_ROOT / name).read_text(encoding="utf-8").strip() for name in _FILES}
if any(not value for value in _TEXT.values()):
    raise RuntimeError("Assistant prompt assets must not be empty")
PROMPT_SHA256 = hashlib.sha256(
    json.dumps(_TEXT, sort_keys=True, ensure_ascii=False).encode("utf-8")
).hexdigest()
SYSTEM_PROMPT = "\n\n".join(_TEXT[name] for name in ("role.md", "evidence.md", "teaching.md", "review.md"))
PURPOSES = {name: _TEXT[f"tasks/{name}.md"] for name in _TASKS}
EXPRESSION_CHART_PROMPT = _TEXT["expression_chart.md"]


def prompt_metadata() -> dict[str, str]:
    return {"version": PROMPT_VERSION, "sha256": PROMPT_SHA256}
