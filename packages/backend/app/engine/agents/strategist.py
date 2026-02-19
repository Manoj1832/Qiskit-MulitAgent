"""
The Strategist — Issue Analyst Agent (Qiskit-Aware).

Responsibilities:
  1. Classify the issue type (Bug, Feature Request, Quantum Correctness, …).
  2. Extract technical clues (errors, files, functions, stack traces).
  3. Determine Qiskit-specific context:
     - Which Qiskit modules are affected.
     - Which quantum-computing domain concepts are involved.
     - Whether this is a user error vs. a library bug.
     - Whether the Rust accelerator layer is involved.
     - Whether floating-point quantum math precision is relevant.
  4. Assess severity, priority, and confidence.
  5. Produce a StrategistOutput for the Architect.

This agent is the *upgraded* version of the standalone `issue_analysis_agent`,
enhanced with Qiskit domain awareness.
"""

from __future__ import annotations

import json
from typing import Any

from .base_agent import BaseAgent
from app.engine.domain.models import (
    GitHubIssueData,
    StrategistOutput,
    SentryOutput,
)
from app.engine.domain.qiskit_knowledge import (
    QISKIT_MODULE_MAP,
    GATE_VS_INSTRUCTION,
    COMMON_BUG_PATTERNS,
    USER_ERROR_SIGNALS,
    LIBRARY_BUG_SIGNALS,
    TRANSPILER_PRESET_LEVELS,
    QUANTUM_PRECISION,
)


class StrategistAgent(BaseAgent):
    """Qiskit-aware issue triage agent."""

    name = "Strategist"

    @property
    def system_prompt(self) -> str:
        # Inject domain knowledge directly into the system prompt
        module_summary = "\n".join(
            f"  • {mod}: {info['description']} (Risk: {info['risk']})"
            for mod, info in QISKIT_MODULE_MAP.items()
        )
        bug_patterns = "\n".join(
            f"  • {bp['pattern']}: {bp['description']}"
            for bp in COMMON_BUG_PATTERNS
        )
        user_err = "\n".join(f"  - {s}" for s in USER_ERROR_SIGNALS)
        lib_bug = "\n".join(f"  - {s}" for s in LIBRARY_BUG_SIGNALS)

        return f"""\
You are **The Strategist** — a senior Qiskit issue-triage engineer in a
multi-agent Software Engineering system.

You DO NOT write code. You DO NOT fix the bug.
You ONLY analyze and understand the issue.

═══ QISKIT DOMAIN KNOWLEDGE ═══

**Repository Modules:**
{module_summary}

**Gate vs Instruction:**
{GATE_VS_INSTRUCTION}

**Transpiler Optimization Levels:**
{TRANSPILER_PRESET_LEVELS}

**Common Bug Patterns in Qiskit:**
{bug_patterns}

**Floating-Point Precision:**
  atol={QUANTUM_PRECISION['atol']}, rtol={QUANTUM_PRECISION['rtol']}
  {QUANTUM_PRECISION['note']}

**User-Error Signals:**
{user_err}

**Library-Bug Signals:**
{lib_bug}

═══ YOUR TASK ═══

Analyze the GitHub issue and produce a structured JSON with:

1. issue_summary — one-line technical summary
2. issue_type — Bug | Feature Request | Performance | Refactor |
   Documentation | Test Failure | Deprecation | Quantum Correctness
3. severity — Critical | High | Medium | Low
4. priority — P0 | P1 | P2 | P3
5. expected_behavior / actual_behavior
6. reproduction_steps
7. technical_clues (error_messages, mentioned_files, mentioned_functions,
   mentioned_classes, keywords, stack_trace)
8. qiskit_context:
   - affected_modules (from the module list above)
   - domain_concepts (e.g. "Gate Definition", "Transpilation Pass", …)
   - is_rust_layer (boolean)
   - is_user_error (boolean)
   - quantum_math_sensitivity (boolean)
   - backwards_compatibility_risk (boolean)
9. suspected_components
10. confidence_level — High | Medium | Low
11. recommended_next_agent — always "Architect"

Return ONLY the JSON object. No markdown fences, no commentary.
"""

    def build_user_prompt(self, **kwargs: Any) -> str:
        issue: GitHubIssueData = kwargs["issue_data"]
        sentry: SentryOutput | None = kwargs.get("sentry_output")

        parts: list[str] = [
            f"Repository: {issue.repo}",
            f"Labels: {', '.join(issue.labels) if issue.labels else 'none'}",
            f"Author: {issue.author}",
            "",
            "=== GitHub Issue ===",
            f"Title: {issue.title}",
            f"Body:\n{issue.body}",
        ]

        if issue.comments:
            parts.append("\n=== Comments ===")
            for i, comment in enumerate(issue.comments[:5], 1):
                parts.append(f"Comment {i}: {comment[:500]}")

        if issue.linked_pr_files:
            parts.append(
                f"\nLinked PR changed files: {', '.join(issue.linked_pr_files)}"
            )

        if sentry:
            if sentry.recent_commits_summary:
                parts.append(f"\n=== Recent Repo Activity ===\n{sentry.recent_commits_summary}")
            if sentry.related_issues:
                parts.append(f"\nRelated issue numbers: {sentry.related_issues}")
            if sentry.repo_structure:
                parts.append(
                    f"\nRelevant directories: {', '.join(sentry.repo_structure[:15])}"
                )

        return "\n".join(parts)

    def parse_response(self, raw: dict[str, Any]) -> StrategistOutput:
        return StrategistOutput(**raw)

    # ── Main entry-point ─────────────────────────────────────────────────

    def run(
        self,
        issue_data: GitHubIssueData,
        sentry_output: SentryOutput | None = None,
    ) -> StrategistOutput:
        """
        Analyze the issue and return structured triage output.
        """
        self.logger.info(
            "🧠 Strategist analyzing issue: %s", issue_data.title
        )

        user_prompt = self.build_user_prompt(
            issue_data=issue_data,
            sentry_output=sentry_output,
        )

        try:
            raw = self.call_llm_json(user_prompt)
            result = self.parse_response(raw)
        except Exception as exc:
            self.logger.error("Strategist analysis failed: %s", exc)
            result = self._create_fallback_output(issue_data)

        self.logger.info(
            "  → Type=%s  Severity=%s  Priority=%s  UserError=%s",
            result.issue_type,
            result.severity,
            result.priority,
            result.qiskit_context.is_user_error if result.qiskit_context else "?",
        )

        return result

    def _create_fallback_output(self, issue: GitHubIssueData) -> StrategistOutput:
        """Create a fallback output if LLM fails."""
        from app.engine.domain.models import TechnicalClues, QiskitContext

        return StrategistOutput(
            issue_summary=f"Analysis failed for: {issue.title}",
            issue_type="Bug",
            severity="Medium",
            priority="P2",
            expected_behavior="Analysis should succeed.",
            actual_behavior="Analysis failed due to LLM error.",
            technical_clues=TechnicalClues(),
            qiskit_context=QiskitContext(),
            suspected_components=[],
            confidence_level="Low",
            recommended_next_agent="Architect"
        )
