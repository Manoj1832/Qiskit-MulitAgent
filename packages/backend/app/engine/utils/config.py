"""
Configuration management — loads settings from environment / .env file.

All agents share these settings.  The `.env` file is expected at the project
root (two levels up from this file, i.e. the `SWE agent/` directory).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Resolve .env relative to the backend root (packages/backend)
# config.py -> utils -> engine -> app -> backend
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_ENV_PATH = _BACKEND_ROOT / ".env"

# Load .env (highest precedence)
load_dotenv(_ENV_PATH, override=True)

# Also load from current working directory as fallback
load_dotenv(override=True)



def get_gemini_api_key() -> str:
    """Return the Google Gemini API key."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set.\n"
            "Copy .env.example → .env and add your Gemini API key.\n"
            "Get one at: https://aistudio.google.com/apikey"
        )
    return key


def get_model_name() -> str:
    """Return the Gemini model name to use."""
    return os.getenv("MODEL_NAME", "gemini-2.0-flash")


def get_github_token() -> Optional[str]:
    """Return the optional GitHub personal-access token."""
    return os.getenv("GITHUB_TOKEN")


def get_max_repair_iterations() -> int:
    """How many times the Developer↔Validator loop can retry."""
    return int(os.getenv("MAX_REPAIR_ITERATIONS", "3"))


def get_qiskit_repo() -> str:
    """Default Qiskit repository to target."""
    return os.getenv("QISKIT_REPO", "Qiskit/qiskit")
