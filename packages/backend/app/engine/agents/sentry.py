"""
The Sentry — Git & PR Reviewer Agent.

Responsibilities:
  1. Fetch GitHub issue data (title, body, labels, comments).
  2. Map the repository structure (key directories, affected files).
  3. Find related issues and recent commits.
  4. Surface PR review comments if a PR is linked.

The Sentry does NOT analyse the issue — it only gathers intelligence.
It feeds its SentryOutput to the Strategist.
"""

from __future__ import annotations

from typing import Any

from .base_agent import BaseAgent
from app.engine.domain.models import SentryOutput, GitHubIssueData
from app.engine.utils.github_helper import (
    fetch_issue,
    fetch_repo_tree,
    fetch_recent_commits,
    search_related_issues,
)


class SentryAgent(BaseAgent):
    """Gathers intelligence about the repo and the issue."""

    name = "Sentry"

    # The Sentry is mostly tool-driven, but uses the LLM to summarise
    # recent commits and identify structurally relevant directories.

    @property
    def system_prompt(self) -> str:
        return """\
You are The Sentry — a code-base reconnaissance agent.

Given a list of recent Git commits and a repository file tree,
your job is to produce a compact summary of:
  1. What has been changing recently in the repo.
  2. Which top-level directories and files are most relevant
     to the issue keywords provided.

Be factual. Do not speculate about the bug.

Return JSON:
{
  "recent_commits_summary": "...",
  "relevant_directories": ["dir1", "dir2"],
  "repo_health_notes": "..."
}
"""

    def build_user_prompt(self, **kwargs: Any) -> str:
        commits = kwargs.get("commits", [])
        tree = kwargs.get("tree", [])
        keywords = kwargs.get("keywords", [])

        parts = [
            "=== Recent Commits ===",
            *[f"  {c['sha']} | {c['message']} ({c['author']})" for c in commits[:15]],
            "",
            "=== Repository Tree (top-level) ===",
            *[f"  {p}" for p in tree[:80]],
            "",
            f"Issue keywords: {', '.join(keywords)}",
        ]
        return "\n".join(parts)

    def parse_response(self, raw: dict[str, Any]) -> dict[str, Any]:
        return raw  # folded into SentryOutput by run()

    # ── Main entry-point ─────────────────────────────────────────────────

    def run(self, repo: str, issue_number: int) -> SentryOutput:
        """
        Gather all intelligence about *repo* issue #*issue_number*.
        """
        self.logger.info(
            "🔍 Sentry scanning %s#%d …", repo, issue_number
        )

        # 1. Fetch issue data
        issue_raw = fetch_issue(repo, issue_number)
        issue_data = GitHubIssueData(**issue_raw)

        # 2. Fetch repo tree
        tree = fetch_repo_tree(repo, max_depth=2)

        # 3. Fetch recent commits
        commits = fetch_recent_commits(repo, max_count=15)

        # 4. Extract keywords from issue for related-issue search
        keywords = (
            issue_data.title.split()[:5]
            + issue_data.labels[:3]
        )

        # 5. Search related issues
        related = search_related_issues(repo, keywords, max_results=5)
        related_issue_nums = [
            r["number"] for r in related
            if r["number"] != issue_number
        ]

        # 6. Use LLM to summarise commits & tree relevance
        user_prompt = self.build_user_prompt(
            commits=commits, tree=tree, keywords=keywords,
        )
        try:
            llm_summary = self.call_llm_json(user_prompt)
        except Exception as exc:
            self.logger.warning("LLM summary failed: %s", exc)
            llm_summary = {
                "recent_commits_summary": "Could not generate summary.",
                "relevant_directories": [],
            }

        return SentryOutput(
            issue_data=issue_data,
            repo_structure=llm_summary.get("relevant_directories", tree[:30]),
            related_issues=related_issue_nums,
            recent_commits_summary=llm_summary.get(
                "recent_commits_summary", ""
            ),
        )
