"""
Test Generator Tool — Auto-generates test suites for PR code changes.

Modeled after PR-Agent's tools/pr_test.py concept:
  - Analyses PR diff to identify testable components
  - Generates complete, runnable test code with fixtures
  - Supports multiple testing frameworks
  - Categorizes tests by type (unit, integration, edge_case)
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
)
from app.engine.utils.llm_client import get_llm_client
from app.tools.pr_reviewer import fetch_pr_diff

logger = logging.getLogger(__name__)


# ── Output Models ────────────────────────────────────────────────────────────

class TestCase(BaseModel):
    """A single generated test case."""
    test_name: str = ""
    test_code: str = ""
    test_description: str = ""
    test_type: str = "unit"  # unit, integration, edge_case
    relevant_file: str = ""
    priority: str = "medium"  # critical, high, medium, low


class TestSuite(BaseModel):
    """A complete test suite for one or more source files."""
    test_file_name: str = ""
    language: str = "python"
    framework: str = "pytest"
    setup_code: str = ""
    test_cases: list[TestCase] = Field(default_factory=list)
    teardown_code: str = ""

    @property
    def full_test_code(self) -> str:
        """Generate the complete, runnable test file content."""
        parts = []
        if self.setup_code:
            parts.append(self.setup_code.strip())
            parts.append("")

        for tc in self.test_cases:
            if tc.test_code:
                parts.append(tc.test_code.strip())
                parts.append("")

        if self.teardown_code:
            parts.append(self.teardown_code.strip())
            parts.append("")

        return "\n\n".join(parts)


class TestGenerationResult(BaseModel):
    """Structured output of the Test Generator tool."""
    test_suites: list[TestSuite] = Field(default_factory=list)
    total_tests: int = 0
    diff_summary: dict = Field(default_factory=dict)
    model_used: str = ""
    error: Optional[str] = None

    @property
    def all_test_code(self) -> str:
        """Combine all test suites into one block."""
        return "\n\n".join(
            f"# === {ts.test_file_name} ===\n{ts.full_test_code}"
            for ts in self.test_suites
            if ts.test_cases
        )


# ── Tool Class ───────────────────────────────────────────────────────────────

class TestGeneratorTool:
    """
    Test Generator — analyses a PR diff and generates comprehensive test suites.

    Creates self-contained, runnable tests targeting the new/modified code.
    """

    def __init__(self):
        self.settings = get_settings("test_generator")
        self.prompts = get_prompt("test_generation_prompts.toml", "test_generation_prompt")
        self.llm = get_llm_client()
        self.model_name = get_settings("config").get("model", "gemini-2.0-flash")

    async def run(
        self,
        repo: str,
        pr_number: int,
        diff_override: Optional[str] = None,
    ) -> TestGenerationResult:
        """
        Generate tests for a PR's code changes.

        Parameters
        ----------
        repo : str
            GitHub repository in "owner/name" format.
        pr_number : int
            The PR number to generate tests for.
        diff_override : str, optional
            Use this diff instead of fetching from GitHub.
        """
        try:
            logger.info("🧪 Test Generator: Analyzing %s#%d", repo, pr_number)

            # 1. Fetch PR data
            pr_data = fetch_pr_diff(repo, pr_number)
            diff_text = diff_override or pr_data["diff"]

            # 2. Parse diff
            patches = parse_diff(diff_text)
            if not patches:
                return TestGenerationResult(
                    model_used=self.model_name,
                    error="No parseable code changes found.",
                )

            diff_summary = get_pr_diff_summary(patches)

            # 3. Format diff
            max_tokens = int(get_settings("config").get("max_model_tokens", 32000) * 0.6)
            formatted_diff = format_diff_for_prompt(patches, max_tokens=max_tokens)

            # 4. Prepare prompt
            prompt = self._prepare_prompt(
                title=pr_data["title"],
                description=pr_data["body"],
                diff=formatted_diff,
                changed_files=pr_data["changed_files"],
            )

            # 5. Call AI model
            test_data = self._call_model(prompt)

            # 6. Structure output
            result = self._format_result(test_data, diff_summary)

            logger.info(
                "✅ Test generation complete: %d test suites, %d total tests",
                len(result.test_suites),
                result.total_tests,
            )
            return result

        except Exception as e:
            logger.error("Test generation failed: %s", e, exc_info=True)
            return TestGenerationResult(
                error=str(e),
                model_used=self.model_name,
            )

    def _prepare_prompt(
        self,
        title: str,
        description: str,
        diff: str,
        changed_files: list[str],
    ) -> dict[str, str]:
        """Render Jinja2 prompt templates."""
        settings = self.settings

        system_template = Template(self.prompts["system"])
        user_template = Template(self.prompts["user"])

        return {
            "system": system_template.render(
                testing_framework=settings.get("testing_framework", "pytest"),
                avoid_mocks=settings.get("avoid_mocks", True),
                extra_instructions=settings.get("extra_instructions", ""),
            ),
            "user": user_template.render(
                title=title,
                description=description,
                diff=diff,
                changed_files=changed_files,
                num_tests=settings.get("num_tests", 5),
            ),
        }

    def _call_model(self, prompt: dict[str, str]) -> dict[str, Any]:
        """Call AI model and parse YAML response."""
        raw_response = self.llm.generate_text(
            user_prompt=prompt["user"],
            system_prompt=prompt["system"],
            temperature=0.3,
        )

        # Extract YAML
        yaml_text = raw_response.strip()
        if "```yaml" in yaml_text:
            yaml_text = yaml_text.split("```yaml")[-1].split("```")[0]
        elif "```" in yaml_text:
            yaml_text = yaml_text.split("```")[1].split("```")[0]

        try:
            parsed = yaml.safe_load(yaml_text)
            if isinstance(parsed, dict):
                return parsed
            return {}
        except yaml.YAMLError as e:
            logger.error("Failed to parse YAML: %s", e)
            return {}

    def _format_result(
        self,
        test_data: dict[str, Any],
        diff_summary: dict,
    ) -> TestGenerationResult:
        """Convert AI response into structured TestGenerationResult."""
        raw_suites = test_data.get("test_suites", [])
        if not isinstance(raw_suites, list):
            raw_suites = []

        test_suites: list[TestSuite] = []
        total_tests = 0

        for raw_suite in raw_suites:
            if not isinstance(raw_suite, dict):
                continue

            # Parse test cases
            raw_cases = raw_suite.get("test_cases", [])
            cases: list[TestCase] = []

            for rc in raw_cases:
                if not isinstance(rc, dict):
                    continue
                try:
                    cases.append(TestCase(
                        test_name=_clean(rc.get("test_name", "")),
                        test_code=rc.get("test_code", "").strip(),
                        test_description=_clean(rc.get("test_description", "")),
                        test_type=_clean(rc.get("test_type", "unit")),
                        relevant_file=_clean(rc.get("relevant_file", "")),
                        priority=_clean(rc.get("priority", "medium")),
                    ))
                except Exception as e:
                    logger.warning("Skipping malformed test case: %s", e)

            if cases:
                test_suites.append(TestSuite(
                    test_file_name=_clean(raw_suite.get("test_file_name", "test_generated.py")),
                    language=_clean(raw_suite.get("language", "python")),
                    framework=_clean(raw_suite.get("framework", "pytest")),
                    setup_code=raw_suite.get("setup_code", "").strip(),
                    test_cases=cases,
                    teardown_code=raw_suite.get("teardown_code", "").strip(),
                ))
                total_tests += len(cases)

        return TestGenerationResult(
            test_suites=test_suites,
            total_tests=total_tests,
            diff_summary=diff_summary,
            model_used=self.model_name,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean(value: str) -> str:
    """Clean YAML block scalar values."""
    return value.strip().replace("\n  ", " ").replace("\n", " ") if value else ""
