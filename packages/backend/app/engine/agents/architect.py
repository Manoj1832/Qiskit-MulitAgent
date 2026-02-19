"""
The Architect — Planner Agent (Cross-File Reasoning).

Responsibilities:
  1. Localize the bug to specific files and line ranges.
  2. Reason across Qiskit module boundaries:
     "If I change the gate definition in `library/`, I must also update
      the transpiler's `basis_set` logic."
  3. Produce a step-by-step implementation plan (PlanSteps).
  4. Identify affected test files.
  5. Flag cross-module impact warnings.

The Architect's ArchitectOutput is the *blueprint* the Developer follows.
"""

from __future__ import annotations

import itertools
import json
from typing import Any, Optional

from .base_agent import BaseAgent
from app.engine.domain.models import (
    ArchitectOutput,
    StrategistOutput,
    SentryOutput,
    FileLocation,
    PlanStep,
)
from app.engine.domain.qiskit_knowledge import (
    QISKIT_MODULE_MAP,
    TRANSPILER_PASS_CATEGORIES,
    TESTING_CONVENTIONS,
    COMMON_BUG_PATTERNS,
)
from app.engine.utils.github_helper import fetch_file_content, search_code_in_repo


class ArchitectAgent(BaseAgent):
    """Plans the implementation by localizing files and reasoning cross-module."""

    name = "Architect"

    @property
    def system_prompt(self) -> str:
        module_risks = "\n".join(
            f"  • {m}: {info['risk']} — key files: {info['key_files']}"
            for m, info in QISKIT_MODULE_MAP.items()
        )
        pass_info = "\n".join(
            f"  • {cat}: {info['description']}"
            for cat, info in TRANSPILER_PASS_CATEGORIES.items()
        )
        tests = json.dumps(TESTING_CONVENTIONS, indent=2)

        return f"""\
You are **The Architect** — a senior Qiskit planning engineer.

You receive:
  • A StrategistOutput (triage) describing the bug.
  • Repository structure information from the Sentry.
  • Optionally, contents of key source files.

Your job is to produce a **detailed implementation plan**.

═══ QISKIT MODULE RISK MAP ═══
{module_risks}

═══ TRANSPILER PASS CATEGORIES ═══
{pass_info}

═══ TESTING CONVENTIONS ═══
{tests}

═══ YOUR TASK ═══

1. **Localize**: Identify the exact files (and approximate line ranges)
   that need to change.  Use the technical clues from the Strategist.

2. **Cross-File Reasoning**: For each change, list other files that MUST
   stay consistent.  Example:
   "If I modify `qiskit/circuit/library/standard_gates/x.py`, I must
    also check `qiskit/transpiler/passes/basis/basis_translator.py`
    and `test/python/circuit/test_gate_definitions.py`."

3. **Plan Steps**: Write numbered steps with:
   - description (what to do)
   - target_files (which files to edit)
   - action (CREATE | MODIFY | DELETE | TEST)
   - cross_file_dependencies
   - risk_notes

4. **Test Plan**: List the test files that should be run and any
   new tests that need to be written.

5. **Impact Assessment**: Rate estimated_complexity (Low/Medium/High)
   and confidence_level (Low/Medium/High).

Return ONLY valid JSON matching this schema:
{{
  "plan_summary": "...",
  "localized_files": [
    {{"file_path": "...", "start_line": N, "end_line": N, "reason": "...", "language": "python"}}
  ],
  "implementation_steps": [
    {{
      "step_number": 1,
      "description": "...",
      "target_files": ["..."],
      "action": "MODIFY",
      "rationale": "...",
      "cross_file_dependencies": ["..."],
      "risk_notes": "..."
    }}
  ],
  "affected_test_files": ["..."],
  "cross_module_impacts": ["..."],
  "estimated_complexity": "Medium",
  "confidence_level": "Medium"
}}

No markdown fences, no commentary.
"""

    def build_user_prompt(self, **kwargs: Any) -> str:
        triage: StrategistOutput = kwargs["strategist_output"]
        sentry: SentryOutput | None = kwargs.get("sentry_output")
        file_contents: dict[str, str] = kwargs.get("file_contents", {})

        parts: list[str] = [
            "=== STRATEGIST TRIAGE ===",
            f"Summary: {triage.issue_summary}",
            f"Type: {triage.issue_type}  |  Severity: {triage.severity}  |  Priority: {triage.priority}",
            f"Expected: {triage.expected_behavior}",
            f"Actual: {triage.actual_behavior}",
        ]

        if triage.technical_clues:
            tc = triage.technical_clues
            if tc.error_messages:
                parts.append(f"Error Messages: {tc.error_messages}")
            if tc.mentioned_files:
                parts.append(f"Mentioned Files: {tc.mentioned_files}")
            if tc.mentioned_functions:
                parts.append(f"Mentioned Functions: {tc.mentioned_functions}")
            if tc.mentioned_classes:
                parts.append(f"Mentioned Classes: {tc.mentioned_classes}")
            if tc.stack_trace:
                parts.append(f"Stack Trace:\n{tc.stack_trace}")

        if triage.qiskit_context:
            qc = triage.qiskit_context
            parts.append(f"\nAffected Modules: {qc.affected_modules}")
            parts.append(f"Domain Concepts: {qc.domain_concepts}")
            parts.append(f"Rust Layer: {qc.is_rust_layer}")
            parts.append(f"Quantum Math Sensitive: {qc.quantum_math_sensitivity}")
            parts.append(f"Backwards Compat Risk: {qc.backwards_compatibility_risk}")

        if triage.suspected_components:
            parts.append(f"Suspected Components: {triage.suspected_components}")

        if sentry:
            if sentry.repo_structure:
                parts.append(
                    f"\n=== REPO STRUCTURE ===\n{chr(10).join(sentry.repo_structure[:40])}"
                )
            if sentry.recent_commits_summary:
                parts.append(
                    f"\n=== RECENT COMMITS ===\n{sentry.recent_commits_summary}"
                )

        if file_contents:
            parts.append("\n=== SOURCE FILE CONTENTS ===")
            for fpath, content in file_contents.items():
                parts.append(f"\n--- {fpath} ---\n{content[:3000]}")

        return "\n".join(parts)

    def parse_response(self, raw: dict[str, Any]) -> ArchitectOutput:
        return ArchitectOutput(**raw)

    # ── Helper: fetch key files for deeper reasoning ─────────────────────

    def _fetch_relevant_files(
        self,
        repo: str,
        triage: StrategistOutput,
    ) -> dict[str, str]:
        """
        Fetch contents of files mentioned in the triage to give
        the Architect concrete code to reason about.
        """
        files_to_fetch: list[str] = []

        # Files mentioned directly
        if triage.technical_clues and triage.technical_clues.mentioned_files:
            mentioned = triage.technical_clues.mentioned_files
            files_to_fetch.extend(itertools.islice(mentioned, 5))

        # Use code search for key functions/classes
        if triage.technical_clues:
            funcs = triage.technical_clues.mentioned_functions or []
            for func in itertools.islice(funcs, 3):
                results = search_code_in_repo(repo, func, language="python", max_results=3)
                for r in results:
                    if r["path"] not in files_to_fetch:
                        files_to_fetch.append(r["path"])

            classes = triage.technical_clues.mentioned_classes or []
            for cls in itertools.islice(classes, 3):
                results = search_code_in_repo(repo, cls, language="python", max_results=3)
                for r in results:
                    if r["path"] not in files_to_fetch:
                        files_to_fetch.append(r["path"])

        # Fetch contents (limit to avoid blowing context)
        contents: dict[str, str] = {}
        for path in itertools.islice(files_to_fetch, 6):
            try:
                content = fetch_file_content(repo, path)
                contents[path] = content[:4000]
            except Exception as exc:
                self.logger.warning("Could not fetch %s: %s", path, exc)

        return contents

    # ── Main entry-point ─────────────────────────────────────────────────

    def run(
        self,
        strategist_output: StrategistOutput,
        sentry_output: SentryOutput | None = None,
        repo: str = "Qiskit/qiskit",
    ) -> ArchitectOutput:
        """
        Produce an implementation plan from the triage output.
        """
        self.logger.info(
            "📐 Architect planning fix for: %s",
            strategist_output.issue_summary,
        )

        # Optionally fetch source files for deeper reasoning
        file_contents: dict[str, str] = {}
        try:
            file_contents = self._fetch_relevant_files(repo, strategist_output)
            if file_contents:
                self.logger.info(
                    "  Fetched %d source files for context",
                    len(file_contents),
                )
        except Exception as exc:
            self.logger.warning("File fetch phase failed: %s", exc)

        user_prompt = self.build_user_prompt(
            strategist_output=strategist_output,
            sentry_output=sentry_output,
            file_contents=file_contents,
        )

        raw = self.call_llm_json(user_prompt)
        result = self.parse_response(raw)

        self.logger.info(
            "  → %d steps, %d files localized, complexity=%s",
            len(result.implementation_steps),
            len(result.localized_files),
            result.estimated_complexity,
        )

        return result
