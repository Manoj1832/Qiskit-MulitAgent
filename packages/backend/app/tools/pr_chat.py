"""
PR Chat Tool — Enables conversational Q&A about Pull Request code.

Architecture:
  PRChatTool
    ├── run(): Main entry point
    │   ├── Fetches PR diff + metadata as context
    │   ├── Builds system prompt with PR context
    │   ├── Appends user message to conversation history
    │   ├── Calls LLM with full chat history
    │   └── Returns AI response
    └── Output: PRChatResponse

Features:
  - Context-aware: PR diff, title, description, and file list are injected
  - Multi-turn: Maintains conversation history for follow-up questions
  - Smart defaults: Provides helpful answers about code quality, bugs, and design
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.tools.pr_reviewer import fetch_pr_diff
from app.algo.pr_processing import parse_diff, format_diff_for_prompt
from app.engine.utils.llm_client import get_llm_client
from app.config_loader import get_settings

logger = logging.getLogger(__name__)


# ── Models ───────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    """A single message in the conversation."""
    role: str = "user"  # "user" or "assistant"
    content: str = ""


class PRChatRequest(BaseModel):
    """Incoming chat request."""
    repo_owner: str
    repo_name: str
    pr_number: int
    message: str
    history: list[ChatMessage] = Field(default_factory=list)
    diff_content: str | None = None  # optional pre-fetched diff


class PRChatResponse(BaseModel):
    """Chat response from the AI."""
    reply: str = ""
    pr_title: str = ""
    files_in_context: list[str] = Field(default_factory=list)
    model_used: str = ""
    error: str | None = None


# ── System Prompt ────────────────────────────────────────────────────────────

CHAT_SYSTEM_PROMPT = """You are an expert code reviewer and software engineering assistant embedded in a GitHub PR review tool.

You are chatting with a developer about a specific Pull Request. You have full access to the PR diff, title, description, and changed files.

## Your Capabilities
- Explain what the PR does and why specific changes were made
- Identify potential bugs, security issues, or performance problems
- Suggest improvements and alternative approaches
- Generate code snippets, tests, or documentation
- Answer questions about coding patterns, best practices, and architecture
- Provide PR descriptions, commit messages, or release notes

## Guidelines
- Be concise but thorough — developers appreciate direct, actionable answers
- When referencing code, quote the specific lines from the diff
- Use markdown formatting for code blocks, lists, and emphasis
- If you're uncertain about something, say so rather than guessing
- Proactively point out issues you notice, but focus on answering the user's question first
- When suggesting code changes, show both the original and improved versions

## PR Context
**Title:** {pr_title}
**Description:** {pr_description}
**Branch:** {pr_branch} → {pr_base_branch}
**Author:** {pr_author}
**Changed Files ({num_files}):** {changed_files}

## PR Diff
```diff
{pr_diff}
```
"""


# ── Tool Class ───────────────────────────────────────────────────────────────

class PRChatTool:
    """
    PR Chat — enables conversational Q&A about Pull Request code.

    Fetches the PR diff as context and uses conversation history
    to enable multi-turn discussions about the code changes.
    """

    def __init__(self):
        self.llm = get_llm_client()
        self.model_name = get_settings("config").get("model", "gemini-2.0-flash")

    async def run(
        self,
        repo: str,
        pr_number: int,
        message: str,
        history: list[ChatMessage] | None = None,
        diff_override: str | None = None,
    ) -> PRChatResponse:
        """
        Process a chat message about a PR.

        Parameters
        ----------
        repo : str
            GitHub repository in "owner/name" format.
        pr_number : int
            The PR number to discuss.
        message : str
            The user's message/question.
        history : list[ChatMessage], optional
            Previous conversation messages for context.
        diff_override : str, optional
            If provided, use this diff instead of fetching from GitHub.
        """
        try:
            logger.info("💬 PR Chat: %s#%d — %s", repo, pr_number, message[:80])

            # 1. Fetch PR data
            pr_data = fetch_pr_diff(repo, pr_number)
            diff_text = diff_override or pr_data["diff"]

            # 2. Parse and format diff (truncate if too large)
            patches = parse_diff(diff_text)
            formatted_diff = format_diff_for_prompt(
                patches,
                max_tokens=int(
                    get_settings("config").get("max_model_tokens", 32000) * 0.5
                ),
            ) if patches else diff_text[:8000]

            # 3. Build system prompt with PR context
            system_prompt = CHAT_SYSTEM_PROMPT.format(
                pr_title=pr_data["title"],
                pr_description=(pr_data["body"] or "No description provided.")[:1000],
                pr_branch=pr_data["branch"],
                pr_base_branch=pr_data.get("base_branch", "main"),
                pr_author=pr_data.get("author", "unknown"),
                num_files=len(pr_data["changed_files"]),
                changed_files=", ".join(pr_data["changed_files"][:30]),
                pr_diff=formatted_diff,
            )

            # 4. Build conversation as a single prompt
            #    (Gemini's generate_content works with a single user prompt)
            conversation_parts = []

            # Include history
            if history:
                for msg in history[-10:]:  # Keep last 10 messages for context
                    prefix = "User" if msg.role == "user" else "Assistant"
                    conversation_parts.append(f"**{prefix}:** {msg.content}")

            # Add current message
            conversation_parts.append(f"**User:** {message}")

            if len(conversation_parts) > 1:
                user_prompt = (
                    "Here is our conversation so far:\n\n"
                    + "\n\n".join(conversation_parts)
                    + "\n\nPlease respond to the latest user message."
                )
            else:
                user_prompt = message

            # 5. Call LLM
            reply = self.llm.generate_text(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.4,
            )

            logger.info("✅ PR Chat response generated (%d chars)", len(reply))

            return PRChatResponse(
                reply=reply,
                pr_title=pr_data["title"],
                files_in_context=pr_data["changed_files"][:20],
                model_used=self.model_name,
            )

        except Exception as e:
            logger.error("PR Chat failed: %s", e, exc_info=True)
            return PRChatResponse(
                reply=f"Sorry, I encountered an error: {str(e)}",
                error=str(e),
                model_used=self.model_name,
            )
