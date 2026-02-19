"""
The Developer — Code Generation & Fixer Agent.

Responsibilities:
  1. Follow the Architect's implementation plan step-by-step.
  2. Generate code changes (unified diffs) for each target file.
  3. Handle Qiskit-specific concerns:
     - Gate unitary correctness.
     - Parameter binding consistency.
     - Python↔Rust boundary awareness.
  4. Participate in the repair loop: receive Validator feedback and
     iterate on the fix.

The Developer produces a DeveloperOutput containing all code changes
as unified diffs that can be applied via `git apply`.
"""

from __future__ import annotations

import itertools
import json
from typing import Any, Optional

from .base_agent import BaseAgent
from app.engine.domain.models import (
    ArchitectOutput,
    StrategistOutput,
    DeveloperOutput,
    ValidatorOutput,
    CodeChange,
)
from app.engine.domain.qiskit_knowledge import (
    GATE_VS_INSTRUCTION,
    QUANTUM_PRECISION,
    TESTING_CONVENTIONS,
)
from app.engine.utils.github_helper import fetch_file_content


class DeveloperAgent(BaseAgent):
    """Writes code patches following the Architect's plan."""

    name = "Developer"

    @property
    def system_prompt(self) -> str:
        return f"""\
You are **The Developer** — a senior Qiskit engineer who writes precise,
minimal, correct code patches.

═══ QISKIT-SPECIFIC CODING RULES ═══

1. **Gate Definitions**:
{GATE_VS_INSTRUCTION}

2. **Floating-Point Precision**:
   - atol = {QUANTUM_PRECISION['atol']}, rtol = {QUANTUM_PRECISION['rtol']}
   - {QUANTUM_PRECISION['note']}
   - NEVER use exact equality (==) for floating-point quantum values.

3. **Transpiler Safety**:
   - If you modify a gate's `.definition`, also verify that 
     `Operator(gate).equiv(Operator(gate.definition))` holds.
   - If you add/remove a standard gate, update the basis translator equivalence library.

4. **Rust Boundary**:
   - Python API changes may require corresponding Rust changes in `crates/`.
   - If the bug is in the Rust layer, note it but provide the Python-side fix.

5. **Code Style**:
   - Follow existing Qiskit conventions (numpy-style docstrings, type annotations).
   - Keep changes minimal — do NOT refactor unrelated code.

═══ YOUR TASK ═══

You receive:
  - An ArchitectOutput with a detailed plan.
  - The original source code of target files.
  - Optionally, feedback from the Validator (if this is a repair iteration).

For each file that needs changes, produce:
  1. `file_path` — the full path in the repo
  2. `original_content` — the relevant section of the original file
  3. `modified_content` — your patched version 
  4. `diff_patch` — a unified diff (--- a/path +++ b/path)
  5. `change_description` — why this change is needed

Also produce:
  - `combined_patch` — all diffs concatenated
  - `explanation` — overall summary of what the patch does
  - `confidence_level` — High | Medium | Low

Return ONLY valid JSON:
{{
  "changes": [
    {{
      "file_path": "...",
      "original_content": "...",
      "modified_content": "...",
      "diff_patch": "...",
      "change_description": "...",
      "language": "python"
    }}
  ],
  "explanation": "...",
  "new_files_created": [],
  "files_deleted": [],
  "combined_patch": "...",
  "iteration": 1,
  "confidence_level": "Medium"
}}

No markdown fences, no commentary.
"""

    def build_user_prompt(self, **kwargs: Any) -> str:
        plan: ArchitectOutput = kwargs["architect_output"]
        triage: StrategistOutput = kwargs["strategist_output"]
        file_contents: dict[str, str] = kwargs.get("file_contents", {})
        validator_feedback: ValidatorOutput | None = kwargs.get("validator_feedback")
        iteration: int = kwargs.get("iteration", 1)

        parts: list[str] = [
            "=== BUG SUMMARY ===",
            f"{triage.issue_summary}",
            f"Type: {triage.issue_type}  Severity: {triage.severity}",
            f"Expected: {triage.expected_behavior}",
            f"Actual: {triage.actual_behavior}",
        ]

        if triage.technical_clues and triage.technical_clues.stack_trace:
            parts.append(f"\nStack Trace:\n{triage.technical_clues.stack_trace}")

        parts.append(f"\n=== IMPLEMENTATION PLAN ===\n{plan.plan_summary}")
        for step in plan.implementation_steps:
            parts.append(
                f"\nStep {step.step_number}: {step.description}\n"
                f"  Action: {step.action}\n"
                f"  Files: {step.target_files}\n"
                f"  Dependencies: {step.cross_file_dependencies}\n"
                f"  Risks: {step.risk_notes}"
            )

        if plan.cross_module_impacts:
            parts.append(
                f"\n⚠️  Cross-Module Impacts:\n"
                + "\n".join(f"  • {imp}" for imp in plan.cross_module_impacts)
            )

        if file_contents:
            parts.append("\n=== SOURCE FILES ===")
            for fpath, content in file_contents.items():
                parts.append(f"\n--- {fpath} ---\n{content[:4000]}")

        # Repair-loop feedback
        if validator_feedback and iteration > 1:
            parts.append(f"\n=== VALIDATOR FEEDBACK (Iteration {iteration}) ===")
            parts.append(f"All tests passed: {validator_feedback.all_tests_passed}")
            parts.append(f"Feedback: {validator_feedback.feedback_for_developer}")

            for tr in validator_feedback.test_results:
                if not tr.passed:
                    parts.append(
                        f"\n  FAILED: {tr.test_name}\n"
                        f"    Error: {tr.error_message}\n"
                        f"    Traceback:\n{tr.traceback[:1000]}"
                    )

            if validator_feedback.quantum_precision_issues:
                parts.append(
                    "\n  ⚠️ Quantum Precision Issues:\n"
                    + "\n".join(f"    • {q}" for q in validator_feedback.quantum_precision_issues)
                )

        parts.append(f"\nThis is iteration {iteration}.")

        return "\n".join(parts)

    def parse_response(self, raw: dict[str, Any]) -> DeveloperOutput:
        return DeveloperOutput(**raw)

    # ── Helper ───────────────────────────────────────────────────────────

    def _fetch_target_files(
        self,
        repo: str,
        plan: ArchitectOutput,
    ) -> dict[str, str]:
        """Fetch the contents of all files referenced in the plan."""
        paths: set[str] = set()
        for loc in plan.localized_files:
            paths.add(loc.file_path)
        for step in plan.implementation_steps:
            paths.update(step.target_files)

        contents: dict[str, str] = {}
        for path in itertools.islice(paths, 8):
            try:
                contents[path] = fetch_file_content(repo, path)
            except Exception as exc:
                self.logger.warning("Could not fetch %s: %s", path, exc)

        return contents

    # ── Main entry-point ─────────────────────────────────────────────────

    def run(
        self,
        architect_output: ArchitectOutput,
        strategist_output: StrategistOutput,
        repo: str = "Qiskit/qiskit",
        validator_feedback: ValidatorOutput | None = None,
        iteration: int = 1,
    ) -> DeveloperOutput:
        """
        Generate code changes following the Architect's plan.

        In repair iterations, incorporates Validator feedback.
        """
        self.logger.info(
            "💻 Developer writing code (iteration %d) …", iteration
        )

        # Fetch source files
        file_contents: dict[str, str] = {}
        try:
            file_contents = self._fetch_target_files(repo, architect_output)
            self.logger.info(
                "  Fetched %d target files", len(file_contents)
            )
        except Exception as exc:
            self.logger.warning("File fetch failed: %s", exc)

        user_prompt = self.build_user_prompt(
            architect_output=architect_output,
            strategist_output=strategist_output,
            file_contents=file_contents,
            validator_feedback=validator_feedback,
            iteration=iteration,
        )

        raw = self.call_llm_json(user_prompt)
        raw["iteration"] = iteration
        result = self.parse_response(raw)

        self.logger.info(
            "  → %d file changes, confidence=%s",
            len(result.changes),
            result.confidence_level,
        )

        return result
