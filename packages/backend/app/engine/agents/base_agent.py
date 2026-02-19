"""
Base agent class — provides shared LLM access, logging, and the `run()` protocol.

Every specialised agent inherits from this and overrides:
  • `system_prompt`  – the instructions that define the agent's personality.
  • `build_user_prompt(...)` – formats the input data into a text prompt.
  • `parse_response(raw)` – converts the LLM response into a Pydantic model.
  • `run(...)` – the public entry-point that orchestrates the above.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from app.engine.utils.llm_client import LLMClient, get_llm_client


class BaseAgent(ABC):
    """Abstract base for every agent in the pipeline."""

    name: str = "BaseAgent"

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or get_llm_client()
        self.logger = logging.getLogger(f"agents.{self.name}")

    # ── To be overridden ─────────────────────────────────────────────────

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the full system prompt for this agent."""
        ...

    @abstractmethod
    def build_user_prompt(self, **kwargs: Any) -> str:
        """Build the user-facing prompt from input data."""
        ...

    @abstractmethod
    def parse_response(self, raw: dict[str, Any]) -> Any:
        """Parse the raw JSON dict into the agent's Pydantic output model."""
        ...

    # ── Convenience ──────────────────────────────────────────────────────

    def call_llm_json(self, user_prompt: str) -> dict[str, Any]:
        """Call the LLM and parse the response as JSON."""
        self.logger.info("Sending prompt to %s LLM …", self.llm.model_name)
        return self.llm.generate_json(
            user_prompt=user_prompt,
            system_prompt=self.system_prompt,
        )

    def call_llm_text(self, user_prompt: str, temperature: float = 0.3) -> str:
        """Call the LLM and return raw text."""
        self.logger.info("Sending prompt to %s LLM …", self.llm.model_name)
        return self.llm.generate_text(
            user_prompt=user_prompt,
            system_prompt=self.system_prompt,
            temperature=temperature,
        )
