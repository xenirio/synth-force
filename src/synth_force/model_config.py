"""Per-agent model configuration via environment variables."""

import os


def get_model(agent_key: str) -> str | None:
    """Return the model for a given agent, or None to use the global MODEL default.

    Looks up MODEL_{AGENT_KEY} first (e.g. MODEL_SE=gemini/gemini-2.5-pro),
    then falls back to None which lets CrewAI use the global MODEL env var.

    Agent keys:
        ANALYST, SENIOR_SE, SE, SE2, QA, DEVOPS
    """
    value = os.environ.get(f"MODEL_{agent_key.upper()}", "").strip()
    return value or None
