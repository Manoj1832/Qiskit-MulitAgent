"""
Code Suggestions Tool — Generates inline code improvement suggestions for a PR.

Modeled after PR-Agent's tools/pr_code_suggestions.py:
  - Analyses each file patch for improvement opportunities
  - Generates concrete replacement code snippets
  - Scores and categorizes suggestions
  - Supports chunk-based processing for large PRs

Architecture:
  CodeSuggestionsTool
    ├── run(): Main orchestration
    │   ├── Fetch PR diff
    │   ├── Process diff chunks (for large PRs)
    │   ├── Call AI model per chunk
    │   └── Merge, deduplicate, and rank suggestions
    └── Output: CodeSuggestionsResult
"""
from __future__ import annotations

import logging
import re
import traceback
from typing import Any, Optional

import yaml
from jinja2 import Template
from pydantic import BaseModel, Field

from app.config_loader import get_settings, get_prompt
from app.algo.pr_processing import (
    parse_diff,
    format_diff_for_prompt,
    get_pr_diff_summary,
    split_diff_for_chunks,
)
from app.engine.utils.llm_client import get_llm_client
from app.tools.pr_reviewer import fetch_pr_diff

logger = logging.getLogger(__name__)


# ── Output Models ────────────────────────────────────────────────────────────

class CodeSuggestion(BaseModel):
    """A single code improvement suggestion."""
    relevant_file: str = ""
    language: str = "python"
    suggestion_content: str = ""
    existing_code: str = ""
    improved_code: str = ""
    one_sentence_summary: str = ""
    label: str = "enhancement"  # bug, security, performance, enhancement, best practice, maintainability
    score: int = Field(default=5, ge=1, le=10)


class CodeSuggestionsResult(BaseModel):
    """Structured output of the Code Suggestions tool."""
    suggestions: list[CodeSuggestion] = Field(default_factory=list)
    total_suggestions: int = 0
    diff_summary: dict = Field(default_factory=dict)
    model_used: str = ""
    chunks_processed: int = 0
    error: Optional[str] = None


# ── Tool Class ───────────────────────────────────────────────────────────────

class CodeSuggestionsTool:
    """
    Code Suggestions — analyses a PR diff and generates actionable code improvements.

    Inspired by PR-Agent's PRCodeSuggestions class. Features:
    - Chunk-based processing for large PRs
    - Suggestion scoring and ranking
    - Deduplication of similar suggestions
    - Category-based organization
    """

    def __init__(self):
        self.settings = get_settings("pr_code_suggestions")
        self.prompts = get_prompt("code_suggestions_prompts.toml", "code_suggestions_prompt")
        self.llm = get_llm_client()
        self.model_name = get_settings("config").get("model", "gemini-2.0-flash")

    async def run(
        self,
        repo: str,
        pr_number: int,
        diff_override: Optional[str] = None,
    ) -> CodeSuggestionsResult:
        """
        Generate code suggestions for a PR.

        Parameters
        ----------
        repo : str
            GitHub repository in "owner/name" format.
        pr_number : int
            The PR number to analyze.
        diff_override : str, optional
            Use this diff instead of fetching from GitHub.
        """
        try:
            logger.info("💡 Code Suggestions: Analyzing %s#%d", repo, pr_number)

            # 1. Fetch PR data
            pr_data = fetch_pr_diff(repo, pr_number)
            diff_text = diff_override or pr_data["diff"]

            # 2. Parse diff
            patches = parse_diff(diff_text)
            if not patches:
                return CodeSuggestionsResult(
                    model_used=self.model_name,
                    error="No parseable code changes found.",
                )

            diff_summary = get_pr_diff_summary(patches)

            # 3. Split into chunks for large PRs
            max_tokens = int(get_settings("config").get("max_model_tokens", 32000) * 0.5)
            chunks = split_diff_for_chunks(patches, max_tokens_per_chunk=max_tokens)

            # 4. Process each chunk
            all_suggestions: list[CodeSuggestion] = []
            max_calls = self.settings.get("max_number_of_calls", 3)

            for i, chunk in enumerate(chunks[:max_calls]):
                logger.info("Processing chunk %d/%d (%d files)", i + 1, len(chunks), len(chunk))

                formatted_diff = format_diff_for_prompt(chunk, max_tokens=max_tokens)

                prompt = self._prepare_prompt(
                    title=pr_data["title"],
                    description=pr_data["body"],
                    diff=formatted_diff,
                )

                chunk_suggestions = self._call_model(prompt)
                all_suggestions.extend(chunk_suggestions)

            # 5. Deduplicate and sort by score
            suggestions = self._deduplicate_suggestions(all_suggestions)
            suggestions.sort(key=lambda s: s.score, reverse=True)

            # 6. Apply score threshold
            threshold = self.settings.get("suggestions_score_threshold", 3)
            suggestions = [s for s in suggestions if s.score >= threshold]

            # 7. Limit count
            per_chunk = self.settings.get("num_code_suggestions_per_chunk", 4)
            suggestions = suggestions[:per_chunk * max_calls]

            logger.info(
                "✅ Code Suggestions complete: %d suggestions from %d chunks",
                len(suggestions),
                len(chunks[:max_calls]),
            )

            return CodeSuggestionsResult(
                suggestions=suggestions,
                total_suggestions=len(suggestions),
                diff_summary=diff_summary,
                model_used=self.model_name,
                chunks_processed=len(chunks[:max_calls]),
            )

        except Exception as e:
            logger.error("Code Suggestions failed: %s", e, exc_info=True)
            return CodeSuggestionsResult(
                error=str(e),
                model_used=self.model_name,
            )

    def _prepare_prompt(
        self,
        title: str,
        description: str,
        diff: str,
    ) -> dict[str, str]:
        """Render Jinja2 prompt templates."""
        extra_instructions = self.settings.get("extra_instructions", "")

        system_template = Template(self.prompts["system"])
        user_template = Template(self.prompts["user"])

        return {
            "system": system_template.render(
                extra_instructions=extra_instructions,
            ),
            "user": user_template.render(
                title=title,
                description=description,
                diff=diff,
            ),
        }

    def _call_model(self, prompt: dict[str, str]) -> list[CodeSuggestion]:
        """Call AI model and parse YAML response into suggestions."""
        raw_response = self.llm.generate_text(
            user_prompt=prompt["user"],
            system_prompt=prompt["system"],
            temperature=0.2,
        )

        # Extract YAML
        yaml_text = raw_response.strip()
        if "```yaml" in yaml_text:
            yaml_text = yaml_text.split("```yaml")[-1].split("```")[0]
        elif "```" in yaml_text:
            yaml_text = yaml_text.split("```")[1].split("```")[0]

        try:
            parsed = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            logger.error("Failed to parse YAML: %s", e)
            return []

        if not isinstance(parsed, dict):
            return []

        raw_suggestions = parsed.get("code_suggestions", [])
        if not isinstance(raw_suggestions, list):
            return []

        suggestions: list[CodeSuggestion] = []
        for s in raw_suggestions:
            if not isinstance(s, dict):
                continue
            try:
                suggestions.append(CodeSuggestion(
                    relevant_file=_clean(s.get("relevant_file", "")),
                    language=_clean(s.get("language", "python")),
                    suggestion_content=_clean(s.get("suggestion_content", "")),
                    existing_code=s.get("existing_code", "").strip(),
                    improved_code=s.get("improved_code", "").strip(),
                    one_sentence_summary=_clean(s.get("one_sentence_summary", "")),
                    label=_clean(s.get("label", "enhancement")),
                    score=_parse_score(s.get("score", 5)),
                ))
            except Exception as e:
                logger.warning("Skipping malformed suggestion: %s", e)

        return suggestions

    def _deduplicate_suggestions(
        self,
        suggestions: list[CodeSuggestion],
    ) -> list[CodeSuggestion]:
        """Remove duplicate suggestions based on file + existing_code."""
        seen: set[str] = set()
        unique: list[CodeSuggestion] = []

        for s in suggestions:
            key = f"{s.relevant_file}:{s.existing_code[:50]}"
            if key not in seen:
                seen.add(key)
                unique.append(s)

        return unique


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean(value: str) -> str:
    """Clean YAML block scalar values."""
    return value.strip().replace("\n  ", " ").replace("\n", " ") if value else ""


def _parse_score(value: Any) -> int:
    """Parse score from various formats."""
    try:
        if isinstance(value, str):
            match = re.search(r"\d+", value.strip())
            if match:
                return max(1, min(10, int(match.group())))
        return max(1, min(10, int(value)))
    except (ValueError, TypeError):
        return 5
