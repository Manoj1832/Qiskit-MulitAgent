"""
Unified LLM client wrapper for the entire SWE-agent framework.

All agents call through this single client so that:
  * API-key management is centralised.
  * Rate-limit retries are handled uniformly.
  * Switching LLM providers is a one-line change.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from google import genai
from google.genai.errors import ClientError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import get_gemini_api_key, get_model_name

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper around Google Gemini with retry logic."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or get_gemini_api_key()
        self.model_name = model_name or get_model_name()
        self.client = genai.Client(api_key=self._api_key)

    # ── Core Generation ──────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(ClientError),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _generate(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = 0.2,
    ) -> str:
        """Send a prompt to Gemini and return the raw text response."""
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=user_prompt,
            config={
                "system_instruction": system_prompt,
                "temperature": temperature,
            },
        )
        return response.text.strip()

    # ── JSON-safe Generation ─────────────────────────────────────────────

    def generate_json(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """
        Generate a response and parse it as JSON.

        Handles common LLM quirks:
          - Stripping markdown code fences.
          - Multiple retry attempts on parse failure.
        """
        raw = self._generate(user_prompt, system_prompt, temperature)
        return self._parse_json(raw)

    def generate_text(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = 0.3,
    ) -> str:
        """Generate a plain-text response (e.g., code, patches)."""
        return self._generate(user_prompt, system_prompt, temperature)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """Strip code fences and parse JSON from LLM output."""
        cleaned = raw.strip()

        # Strip ```json ... ``` or ``` ... ```
        if cleaned.startswith("```"):
            # Remove opening fence (possibly with language tag)
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("LLM returned invalid JSON:\n%.500s", cleaned)
            raise ValueError(
                "LLM did not return valid JSON. Raw output starts with: "
                f"{cleaned[:200]!r}"
            ) from exc


# ── Module-level convenience ──────────────────────────────────────────────────

_default_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Return (and lazily create) a shared LLMClient instance."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
