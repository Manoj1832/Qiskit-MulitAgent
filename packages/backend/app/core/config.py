"""
API-level configuration — JWT, CORS, and server settings.
Extends the existing utils/config.py for agent settings.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env", override=True)

# ── JWT ──────────────────────────────────────────────────────────────────────
JWT_SECRET: str = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24h

# ── Extension token (shared secret between extension and backend) ─────────────
EXTENSION_API_KEY: str = os.getenv("EXTENSION_API_KEY", "swe-agent-dev-key-change-in-prod")

# ── CORS ─────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS: list[str] = [
    "chrome-extension://*",
    "http://localhost:3000",
    "http://localhost:8000",
    "null",  # Chrome extensions send Origin: null
]

# ── Server ───────────────────────────────────────────────────────────────────
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# ── GitHub ───────────────────────────────────────────────────────────────────
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
