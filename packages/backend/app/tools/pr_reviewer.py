"""
PR Reviewer Tool — Provides comprehensive PR review with key issues, security analysis, and scoring.

Modeled after PR-Agent's tools/pr_reviewer.py:
  - Processes PR diff into structured hunks
  - Renders Jinja2 prompt templates with PR context
  - Calls AI model and parses YAML response
  - Returns structured review with issues, scores, and findings

Architecture:
  PRReviewerTool
    ├── __init__(): Load settings & prompts
    ├── run(): Main orchestration
    │   ├── _fetch_pr_data(): Get PR diff from GitHub
    │   ├── _prepare_prompt(): Render Jinja2 templates
    │   ├── _call_model(): Call AI and parse YAML
    │   └── _format_review(): Structure the output
    └── Output: PRReviewResult (Pydantic model)
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
from app.engine.utils.github_helper import _get, GITHUB_API, _headers

logger = logging.getLogger(__name__)


# ── Output Models ────────────────────────────────────────────────────────────

class KeyIssue(BaseModel):
    """A key issue found during review."""
    relevant_file: str = ""
    issue_header: str = ""
    issue_content: str = ""
    start_line: int = 0
    end_line: int = 0
    severity: str = "minor"  # critical, major, minor, suggestion


class PRReviewResult(BaseModel):
    """Structured output of the PR Review tool."""
    # Review scores
    estimated_effort: int = Field(default=3, ge=1, le=5)
    score: int = Field(default=70, ge=0, le=100)
    relevant_tests: str = "No"
    summary: str = ""

    # Findings
    key_issues: list[KeyIssue] = Field(default_factory=list)
    security_concerns: str = "No"

    # Metadata
    diff_summary: dict = Field(default_factory=dict)
    model_used: str = ""
    error: Optional[str] = None


# ── GitHub PR Data Fetcher ───────────────────────────────────────────────────

def fetch_pr_diff(repo: str, pr_number: int) -> dict[str, Any]:
    """
    Fetch PR metadata and diff from GitHub.

    Returns dict with: title, body, branch, diff, files, commits
    """
    logger.info("Fetching PR #%d from %s", pr_number, repo)

    # PR metadata
    pr_data = _get(f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}")

    # PR diff (accept header for unified diff)
    import requests
    headers = _headers()
    headers["Accept"] = "application/vnd.github.v3.diff"
    diff_resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
        headers=headers,
        timeout=30,
    )
    diff_resp.raise_for_status()
    diff_text = diff_resp.text

    # PR files list
    files_data = _get(f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/files")
    changed_files = [f["filename"] for f in files_data]

    # Commit messages
    commits_data = _get(f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/commits")
    commit_messages = "\n".join(
        c.get("commit", {}).get("message", "").split("\n")[0]
        for c in commits_data[:20]
    )

    return {
        "title": pr_data.get("title", ""),
        "body": pr_data.get("body", "") or "",
        "branch": pr_data.get("head", {}).get("ref", ""),
        "base_branch": pr_data.get("base", {}).get("ref", ""),
        "diff": diff_text,
        "changed_files": changed_files,
        "commit_messages": commit_messages,
        "author": pr_data.get("user", {}).get("login", ""),
        "state": pr_data.get("state", ""),
        "labels": [l["name"] for l in pr_data.get("labels", [])],
    }


# ── Tool Class ───────────────────────────────────────────────────────────────

class PRReviewerTool:
    """
    PR Reviewer — analyses a pull request and generates a structured review.

    Inspired by PR-Agent's PRReviewer class. Orchestrates:
    1. Fetching PR diff from GitHub
    2. Parsing diff into structured hunks
    3. Rendering prompt templates
    4. Calling AI model
    5. Parsing YAML response into structured output
    """

    def __init__(self):
        self.settings = get_settings("pr_reviewer")
        self.prompts = get_prompt("pr_reviewer_prompts.toml", "pr_review_prompt")
        self.llm = get_llm_client()
        self.model_name = get_settings("config").get("model", "gemini-2.0-flash")

    async def run(
        self,
        repo: str,
        pr_number: int,
        diff_override: Optional[str] = None,
    ) -> PRReviewResult:
        """
        Execute the full PR review pipeline.

        Parameters
        ----------
        repo : str
            GitHub repository in "owner/name" format.
        pr_number : int
            The PR number to review.
        diff_override : str, optional
            If provided, use this diff instead of fetching from GitHub.
        """
        try:
            # 1. Fetch PR data
            logger.info("🔍 PR Reviewer: Starting review of %s#%d", repo, pr_number)
            pr_data = fetch_pr_diff(repo, pr_number)

            # Use override if provided
            diff_text = diff_override or pr_data["diff"]

            # 2. Parse diff into structured patches
            patches = parse_diff(diff_text)
            if not patches:
                return PRReviewResult(
                    summary="PR has no parseable code changes.",
                    diff_summary={"total_files": 0},
                    model_used=self.model_name,
                )

            diff_summary = get_pr_diff_summary(patches)

            # 3. Format diff for prompt
            formatted_diff = format_diff_for_prompt(
                patches,
                max_tokens=int(get_settings("config").get("max_model_tokens", 32000) * 0.6),
            )

            # 4. Render prompt templates
            prompt = self._prepare_prompt(
                title=pr_data["title"],
                description=pr_data["body"],
                branch=pr_data["branch"],
                diff=formatted_diff,
                commit_messages=pr_data.get("commit_messages", ""),
            )

            # 5. Call AI model
            review_data = self._call_model(prompt)

            # 6. Structure the output
            result = self._format_review(review_data, diff_summary)
            logger.info(
                "✅ PR Review complete: score=%d, issues=%d",
                result.score,
                len(result.key_issues),
            )
            return result

        except Exception as e:
            logger.error("PR Review failed: %s", e, exc_info=True)
            return PRReviewResult(
                summary=f"Review failed: {str(e)}",
                error=str(e),
                model_used=self.model_name,
            )

    def _prepare_prompt(
        self,
        title: str,
        description: str,
        branch: str,
        diff: str,
        commit_messages: str = "",
    ) -> dict[str, str]:
        """Render Jinja2 prompt templates with PR context."""
        extra_instructions = self.settings.get("extra_instructions", "")

        system_template = Template(self.prompts["system"])
        user_template = Template(self.prompts["user"])

        system_prompt = system_template.render(
            extra_instructions=extra_instructions,
            require_estimate_effort_to_review=self.settings.get("require_estimate_effort_to_review", True),
            require_score=self.settings.get("require_score_review", True),
            require_tests=self.settings.get("require_tests_review", True),
            require_security_review=self.settings.get("require_security_review", True),
            require_can_be_split_review=self.settings.get("require_can_be_split_review", False),
            num_max_findings=self.settings.get("num_max_findings", 5),
        )

        user_prompt = user_template.render(
            title=title,
            description=description,
            branch=branch,
            diff=diff,
            commit_messages=commit_messages,
        )

        return {"system": system_prompt, "user": user_prompt}

    def _call_model(self, prompt: dict[str, str]) -> dict[str, Any]:
        """Call the AI model and parse the YAML response."""
        logger.info("Calling AI model for PR review...")

        raw_response = self.llm.generate_text(
            user_prompt=prompt["user"],
            system_prompt=prompt["system"],
            temperature=0.2,
        )

        # Extract YAML from response (handle ```yaml ... ``` blocks)
        yaml_text = raw_response.strip()
        if "```yaml" in yaml_text:
            yaml_text = yaml_text.split("```yaml")[-1].split("```")[0]
        elif "```" in yaml_text:
            yaml_text = yaml_text.split("```")[1].split("```")[0]

        try:
            parsed = yaml.safe_load(yaml_text)
            if isinstance(parsed, dict):
                return parsed
            else:
                logger.warning("YAML parsed to non-dict: %s", type(parsed))
                return {"review": {}}
        except yaml.YAMLError as e:
            logger.error("Failed to parse YAML response: %s", e)
            logger.debug("Raw response:\n%s", raw_response[:500])
            return {"review": {"summary": raw_response[:500]}}

    def _format_review(
        self,
        review_data: dict[str, Any],
        diff_summary: dict,
    ) -> PRReviewResult:
        """Convert raw AI response into structured PRReviewResult."""
        review = review_data.get("review", review_data)

        # Parse key issues
        key_issues: list[KeyIssue] = []
        raw_issues = review.get("key_issues_to_review", [])
        if isinstance(raw_issues, list):
            for issue in raw_issues:
                if isinstance(issue, dict):
                    key_issues.append(KeyIssue(
                        relevant_file=_clean_yaml_value(issue.get("relevant_file", "")),
                        issue_header=_clean_yaml_value(issue.get("issue_header", "")),
                        issue_content=_clean_yaml_value(issue.get("issue_content", "")),
                        start_line=int(issue.get("start_line", 0)),
                        end_line=int(issue.get("end_line", 0)),
                        severity=_clean_yaml_value(issue.get("severity", "minor")),
                    ))

        # Parse effort estimate
        effort_raw = review.get("estimated_effort_to_review_[1-5]", 3)
        effort = _parse_int(effort_raw, default=3, min_val=1, max_val=5)

        # Parse score
        score_raw = review.get("score", 70)
        score = _parse_int(score_raw, default=70, min_val=0, max_val=100)

        return PRReviewResult(
            estimated_effort=effort,
            score=score,
            relevant_tests=_clean_yaml_value(str(review.get("relevant_tests", "No"))),
            summary=_clean_yaml_value(str(review.get("summary", ""))),
            key_issues=key_issues,
            security_concerns=_clean_yaml_value(str(review.get("security_concerns", "No"))),
            diff_summary=diff_summary,
            model_used=self.model_name,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean_yaml_value(value: str) -> str:
    """Clean YAML block scalar values (strip whitespace, newlines)."""
    if not value:
        return ""
    return value.strip().replace("\n  ", " ").replace("\n", " ")


def _parse_int(value: Any, default: int = 0, min_val: int = 0, max_val: int = 100) -> int:
    """Safely parse an integer from various YAML value formats."""
    try:
        if isinstance(value, str):
            value = value.strip()
            # Extract first number from string
            match = re.search(r"\d+", value)
            if match:
                value = int(match.group())
            else:
                return default
        return max(min_val, min(max_val, int(value)))
    except (ValueError, TypeError):
        return default
