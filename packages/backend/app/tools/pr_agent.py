"""
PR Agent — Main command dispatcher, modeled after PR-Agent's agent/pr_agent.py.

Maps slash-style commands to tool classes:
  /review  → PRReviewerTool
  /improve → CodeSuggestionsTool
  /test    → TestGeneratorTool

Usage:
    agent = PRAgentDispatcher()
    result = await agent.handle_request(
        pr_url="https://github.com/owner/repo/pull/123",
        command="/review",
    )
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.tools.pr_reviewer import PRReviewerTool
from app.tools.code_suggestions import CodeSuggestionsTool
from app.tools.test_generator import TestGeneratorTool

logger = logging.getLogger(__name__)


# ── Command → Tool Mapping ──────────────────────────────────────────────────

COMMAND_MAP: dict[str, type] = {
    "/review": PRReviewerTool,
    "/improve": CodeSuggestionsTool,
    "/suggest": CodeSuggestionsTool,
    "/test": TestGeneratorTool,
    "/tests": TestGeneratorTool,
    "/generate_tests": TestGeneratorTool,
}

COMMAND_DESCRIPTIONS: dict[str, str] = {
    "/review": "Comprehensive PR review with issues, scoring, and security analysis",
    "/improve": "Generate inline code improvement suggestions",
    "/test": "Auto-generate test suites for changed code",
}


# ── URL Parser ───────────────────────────────────────────────────────────────

_PR_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+)/pull/(\d+)"
)


def parse_pr_url(url: str) -> tuple[str, int]:
    """
    Extract repo and PR number from a GitHub PR URL.

    Returns: (repo "owner/name", pr_number)
    Raises: ValueError if URL doesn't match expected pattern
    """
    match = _PR_URL_RE.search(url)
    if not match:
        raise ValueError(f"Invalid GitHub PR URL: {url}")
    owner, name, pr_num = match.groups()
    return f"{owner}/{name}", int(pr_num)


# ── Dispatcher ───────────────────────────────────────────────────────────────

class PRAgentDispatcher:
    """
    Main entry point for PR-Agent style command processing.

    Parses the command, instantiates the appropriate tool, and runs it.
    """

    def __init__(self):
        self.command_map = COMMAND_MAP

    async def handle_request(
        self,
        pr_url: str,
        command: str,
        args: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Handle a PR-Agent command.

        Parameters
        ----------
        pr_url : str
            Full GitHub PR URL or "owner/repo" + pr_number encoded.
        command : str
            The command to execute (e.g., "/review", "/improve", "/test").
        args : dict, optional
            Additional arguments to pass to the tool.

        Returns
        -------
        dict
            The tool's result serialized as a dictionary.
        """
        try:
            logger.info("🤖 PR Agent: Handling command '%s' for %s", command, pr_url)

            # Normalize command
            command = command.strip().lower()
            if not command.startswith("/"):
                command = f"/{command}"

            # Validate command
            tool_class = self.command_map.get(command)
            if not tool_class:
                return {
                    "error": f"Unknown command: {command}",
                    "available_commands": list(COMMAND_DESCRIPTIONS.keys()),
                    "descriptions": COMMAND_DESCRIPTIONS,
                }

            # Parse PR URL
            repo, pr_number = parse_pr_url(pr_url)

            # Instantiate and run tool
            tool = tool_class()
            result = await tool.run(repo=repo, pr_number=pr_number)

            # Serialize result
            return result.model_dump()

        except ValueError as e:
            logger.error("Invalid request: %s", e)
            return {"error": str(e)}
        except Exception as e:
            logger.error("PR Agent failed: %s", e, exc_info=True)
            return {"error": f"Internal error: {str(e)}"}

    def get_available_commands(self) -> dict[str, str]:
        """Return available commands and their descriptions."""
        return COMMAND_DESCRIPTIONS
