"""
The Validator — Testing & Verification Agent.

Responsibilities:
  1. Review the Developer's code changes for correctness.
  2. Identify which existing tests should be run.
  3. Write NEW test cases for the fix.
  4. Handle Qiskit-specific validation:
     - Floating-point tolerance in quantum-state comparisons.
     - Gate unitary consistency checks.
     - Transpiler round-trip validation.
  5. Provide structured feedback to the Developer for repair iterations.

The Validator produces a ValidatorOutput that either approves the fix
or sends actionable feedback back to the Developer.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .base_agent import BaseAgent
from app.engine.domain.models import (
    DeveloperOutput,
    ArchitectOutput,
    StrategistOutput,
    ValidatorOutput,
    TestResult,
)
from app.engine.domain.qiskit_knowledge import (
    QUANTUM_PRECISION,
    TESTING_CONVENTIONS,
    COMMON_BUG_PATTERNS,
)


class ValidatorAgent(BaseAgent):
    """Reviews code changes, runs tests, and provides repair feedback."""

    name = "Validator"

    @property
    def system_prompt(self) -> str:
        test_info = json.dumps(TESTING_CONVENTIONS, indent=2)

        return f"""\
You are **The Validator** — a senior Qiskit QA engineer and test specialist.

You receive:
  - The Developer's code changes (DeveloperOutput).
  - The Architect's plan (for context).
  - The Strategist's triage (for context).

═══ QISKIT TESTING KNOWLEDGE ═══

{test_info}

═══ QUANTUM-SPECIFIC VALIDATION RULES ═══

1. **Floating-Point Tolerance**:
   - atol = {QUANTUM_PRECISION['atol']}, rtol = {QUANTUM_PRECISION['rtol']}
   - Use `numpy.allclose(a, b, atol=..., rtol=...)` or `Operator.equiv()`.
   - Flag any test that uses exact equality (==) on quantum states.

2. **Gate Unitary Checks**:
   - For any modified gate, verify `Operator(gate) ≈ Operator(gate.definition)`.
   - Check that `gate.inverse()` satisfies `gate @ gate.inverse() ≈ I`.
   - For controlled gates, verify that the control-target structure is correct.

3. **Transpiler Round-Trip**:
   - If transpiler-related, verify that transpiling the circuit at
     optimization levels 0, 1, 2, 3 all produce equivalent results.
   - Use `Operator(original_circuit).equiv(Operator(transpiled_circuit))`.

4. **DAG Consistency**:
   - After converting QuantumCircuit → DAG → QuantumCircuit, the result
     must be equivalent to the original.

5. **Regression Detection**:
   - Check if the fix could break any of the common bug patterns.
   - If the fix modifies a public API, check backwards compatibility.

═══ YOUR TASK ═══

Analyze the code changes and produce a validation report as JSON:
{{
  "all_tests_passed": true/false,
  "test_results": [
    {{
      "test_name": "...",
      "passed": true/false,
      "error_message": "...",
      "traceback": "...",
      "duration_seconds": 0.0
    }}
  ],
  "new_tests_written": [
    "test code as string..."
  ],
  "regression_detected": true/false,
  "quantum_precision_issues": [
    "description of precision concern..."
  ],
  "feedback_for_developer": "Actionable feedback if tests fail...",
  "iteration": 1
}}

For `new_tests_written`, write complete pytest test functions that
validate the fix.

For `test_results`, evaluate each code change by reasoning about whether
it would pass Qiskit's test suite. Simulate test execution based on your
domain knowledge.

For `feedback_for_developer`, be specific:
  - Which exact line/function has the issue.
  - What the expected vs actual behavior would be.
  - Suggest a concrete fix.

No markdown fences, no commentary. Return ONLY the JSON.
"""

    def build_user_prompt(self, **kwargs: Any) -> str:
        dev_output: DeveloperOutput = kwargs["developer_output"]
        plan: ArchitectOutput = kwargs["architect_output"]
        triage: StrategistOutput = kwargs["strategist_output"]
        iteration: int = kwargs.get("iteration", 1)

        parts: list[str] = [
            "=== BUG CONTEXT ===",
            f"Summary: {triage.issue_summary}",
            f"Type: {triage.issue_type}  Severity: {triage.severity}",
            f"Expected: {triage.expected_behavior}",
            f"Actual: {triage.actual_behavior}",
        ]

        if triage.qiskit_context:
            qc = triage.qiskit_context
            parts.append(f"Affected Modules: {qc.affected_modules}")
            parts.append(f"Quantum Math Sensitive: {qc.quantum_math_sensitivity}")

        parts.append(f"\n=== PLAN ({len(plan.implementation_steps)} steps) ===")
        parts.append(plan.plan_summary)

        if plan.affected_test_files:
            parts.append(f"\nTest files to run: {plan.affected_test_files}")

        parts.append(f"\n=== CODE CHANGES (Iteration {iteration}) ===")
        parts.append(f"Developer explanation: {dev_output.explanation}")

        for change in dev_output.changes:
            parts.append(
                f"\n--- Change: {change.file_path} ---\n"
                f"Description: {change.change_description}\n"
                f"Language: {change.language}\n"
            )
            if change.diff_patch:
                parts.append(f"Diff:\n{change.diff_patch[:3000]}")
            elif change.modified_content:
                parts.append(f"Modified content:\n{change.modified_content[:3000]}")

        if dev_output.combined_patch:
            parts.append(
                f"\n=== COMBINED PATCH ===\n{dev_output.combined_patch[:5000]}"
            )

        if plan.cross_module_impacts:
            parts.append(
                "\n⚠️ Cross-Module Impacts to validate:\n"
                + "\n".join(f"  • {imp}" for imp in plan.cross_module_impacts)
            )

        return "\n".join(parts)

    def parse_response(self, raw: dict[str, Any]) -> ValidatorOutput:
        return ValidatorOutput(**raw)

    # ── Main entry-point ─────────────────────────────────────────────────

    def run(
        self,
        developer_output: DeveloperOutput,
        architect_output: ArchitectOutput,
        strategist_output: StrategistOutput,
        iteration: int = 1,
    ) -> ValidatorOutput:
        """
        Validate the Developer's code changes and provide feedback.
        """
        self.logger.info(
            "✅ Validator reviewing changes (iteration %d) …", iteration
        )

        user_prompt = self.build_user_prompt(
            developer_output=developer_output,
            architect_output=architect_output,
            strategist_output=strategist_output,
            iteration=iteration,
        )

        raw = self.call_llm_json(user_prompt)
        raw["iteration"] = iteration
        result = self.parse_response(raw)

        passed_count = sum(1 for t in result.test_results if t.passed)
        total_count = len(result.test_results)

        self.logger.info(
            "  → Tests: %d/%d passed | Regression: %s | Precision issues: %d",
            passed_count,
            total_count,
            result.regression_detected,
            len(result.quantum_precision_issues),
        )

        return result
