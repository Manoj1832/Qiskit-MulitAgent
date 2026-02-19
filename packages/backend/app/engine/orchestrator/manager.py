"""
Central Manager — Hierarchical Multi-Agent Orchestrator.

This is the brain of the SWE-agent framework.  It:

  1. Receives an issue (repo + number).
  2. Delegates to the **Sentry** to gather intelligence.
  3. Delegates to the **Strategist** to triage the issue.
  4. If the Strategist determines it's a user error → stops with advice.
  5. Delegates to the **Architect** to create an implementation plan.
  6. Delegates to the **Developer** to generate code.
  7. Delegates to the **Validator** to verify the fix.
  8. If validation fails → loops back to step 6 (repair loop, max N iterations).
  9. On success → outputs the final patch.

The Manager never talks to the LLM directly — it only coordinates agents
and validates the data flowing between them.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.engine.agents.sentry import SentryAgent
from app.engine.agents.strategist import StrategistAgent
from app.engine.agents.architect import ArchitectAgent
from app.engine.agents.developer import DeveloperAgent
from app.engine.agents.validator import ValidatorAgent
from app.engine.domain.models import (
    PipelineRun,
    PipelineStatus,
    StrategistOutput,
)
from app.engine.utils.config import get_max_repair_iterations

logger = logging.getLogger(__name__)
console = Console()


class CentralManager:
    """
    Hierarchical orchestrator that coordinates the agent pipeline.

    Usage::

        manager = CentralManager()
        result = manager.run(repo="Qiskit/qiskit", issue_number=12345)
        print(result.final_patch)
    """

    def __init__(self) -> None:
        self.sentry = SentryAgent()
        self.strategist = StrategistAgent()
        self.architect = ArchitectAgent()
        self.developer = DeveloperAgent()
        self.validator = ValidatorAgent()
        self.max_iterations = get_max_repair_iterations()

    # ── Pipeline Execution ───────────────────────────────────────────────

    def run(
        self,
        repo: str,
        issue_number: int,
        skip_sentry: bool = False,
    ) -> PipelineRun:
        """
        Execute the full issue-to-patch pipeline.

        Parameters
        ----------
        repo : str
            GitHub repository in ``owner/name`` format.
        issue_number : int
            The GitHub issue number to fix.
        skip_sentry : bool
            If True, skip the Sentry phase (useful for testing with
            pre-existing issue data).

        Returns
        -------
        PipelineRun
            Full pipeline result including all agent outputs and the final patch.
        """
        run_id = str(uuid.uuid4())[:8]
        pipeline = PipelineRun(
            run_id=run_id,
            repo=repo,
            issue_number=issue_number,
            started_at=datetime.now(timezone.utc),
        )

        self._print_header(pipeline)

        try:
            # ── Phase 1: Reconnaissance (Sentry) ─────────────────────
            pipeline.status = PipelineStatus.TRIAGE
            self._print_phase("Phase 1: Reconnaissance", "🔍")

            if not skip_sentry:
                sentry_output = self.sentry.run(repo, issue_number)
                pipeline.sentry_output = sentry_output
                self._print_sentry_summary(sentry_output)
            else:
                sentry_output = None
                console.print("  [dim]Sentry phase skipped.[/dim]")

            # ── Phase 2: Issue Triage (Strategist) ───────────────────
            self._print_phase("Phase 2: Issue Triage", "🧠")

            if sentry_output and sentry_output.issue_data:
                issue_data = sentry_output.issue_data
            else:
                # Fallback: fetch issue directly
                from app.engine.utils.github_helper import fetch_issue
                from app.engine.domain.models import GitHubIssueData
                raw = fetch_issue(repo, issue_number)
                issue_data = GitHubIssueData(**raw)

            strategist_output = self.strategist.run(
                issue_data=issue_data,
                sentry_output=sentry_output,
            )
            pipeline.strategist_output = strategist_output
            self._print_strategist_summary(strategist_output)

            # ── Gate: User Error Check ───────────────────────────────
            if (
                strategist_output.qiskit_context
                and strategist_output.qiskit_context.is_user_error
            ):
                console.print(
                    Panel(
                        "[yellow]⚠️  The Strategist determined this is a "
                        "USER ERROR, not a library bug.\n\n"
                        f"Summary: {strategist_output.issue_summary}\n\n"
                        "Pipeline stopped — no code changes needed.[/yellow]",
                        title="User Error Detected",
                        border_style="yellow",
                    )
                )
                pipeline.status = PipelineStatus.COMPLETED
                pipeline.error_log.append(
                    "Stopped: issue classified as user error."
                )
                pipeline.completed_at = datetime.now(timezone.utc)
                return pipeline

            # ── Phase 3: Planning (Architect) ────────────────────────
            pipeline.status = PipelineStatus.PLANNING
            self._print_phase("Phase 3: Implementation Planning", "📐")

            architect_output = self.architect.run(
                strategist_output=strategist_output,
                sentry_output=sentry_output,
                repo=repo,
            )
            pipeline.architect_output = architect_output
            self._print_architect_summary(architect_output)

            # ── Phase 4+5: Code → Validate Loop ─────────────────────
            pipeline.status = PipelineStatus.CODING
            iteration = 0
            validator_feedback = None

            while iteration < self.max_iterations:
                iteration += 1
                pipeline.repair_iterations = iteration

                # ── 4. Code Generation (Developer) ───────────────────
                self._print_phase(
                    f"Phase 4: Code Generation (Iteration {iteration})",
                    "💻",
                )

                developer_output = self.developer.run(
                    architect_output=architect_output,
                    strategist_output=strategist_output,
                    repo=repo,
                    validator_feedback=validator_feedback,
                    iteration=iteration,
                )
                pipeline.developer_output = developer_output
                self._print_developer_summary(developer_output)

                # ── 5. Validation (Validator) ────────────────────────
                pipeline.status = PipelineStatus.VALIDATING
                self._print_phase(
                    f"Phase 5: Validation (Iteration {iteration})",
                    "✅",
                )

                validator_output = self.validator.run(
                    developer_output=developer_output,
                    architect_output=architect_output,
                    strategist_output=strategist_output,
                    iteration=iteration,
                )
                pipeline.validator_output = validator_output
                self._print_validator_summary(validator_output)

                # ── Check: All tests passed? ─────────────────────────
                if validator_output.all_tests_passed and not validator_output.regression_detected:
                    console.print(
                        "\n  [green]✅ All tests passed! Fix verified.[/green]\n"
                    )
                    break

                # Prepare feedback for repair loop
                validator_feedback = validator_output
                console.print(
                    f"\n  [yellow]⚠️  Tests failed — entering repair "
                    f"iteration {iteration + 1}/{self.max_iterations}[/yellow]\n"
                )
                pipeline.status = PipelineStatus.CODING

            # ── Finalize ─────────────────────────────────────────────
            if developer_output.combined_patch:
                pipeline.final_patch = developer_output.combined_patch
            elif developer_output.changes:
                pipeline.final_patch = "\n\n".join(
                    c.diff_patch for c in developer_output.changes if c.diff_patch
                )

            pipeline.status = PipelineStatus.COMPLETED
            pipeline.completed_at = datetime.now(timezone.utc)
            self._print_final_report(pipeline)

        except Exception as exc:
            pipeline.status = PipelineStatus.FAILED
            pipeline.error_log.append(str(exc))
            pipeline.completed_at = datetime.now(timezone.utc)
            console.print(
                Panel(
                    f"[red]❌ Pipeline failed: {exc}[/red]",
                    title="Error",
                    border_style="red",
                )
            )
            logger.exception("Pipeline failed")

        return pipeline

    # ── Pretty Printing ──────────────────────────────────────────────────

    def _print_header(self, pipeline: PipelineRun) -> None:
        console.print()
        console.print(
            Panel(
                f"[bold cyan]Qiskit SWE-Agent Pipeline[/bold cyan]\n\n"
                f"Run ID:  {pipeline.run_id}\n"
                f"Repo:    {pipeline.repo}\n"
                f"Issue:   #{pipeline.issue_number}\n"
                f"Started: {pipeline.started_at}",
                title="🤖 Multi-Agent Orchestrator",
                border_style="cyan",
            )
        )

    def _print_phase(self, title: str, emoji: str) -> None:
        console.print(f"\n{'─' * 60}")
        console.print(f"  {emoji}  [bold]{title}[/bold]")
        console.print(f"{'─' * 60}")

    def _print_sentry_summary(self, output) -> None:
        if output.issue_data:
            console.print(f"  Issue: [bold]{output.issue_data.title}[/bold]")
            console.print(f"  Labels: {', '.join(output.issue_data.labels) or 'none'}")
            console.print(f"  Author: {output.issue_data.author}")
        console.print(f"  Repo structure: {len(output.repo_structure)} entries")
        console.print(f"  Related issues: {output.related_issues or 'none'}")

    def _print_strategist_summary(self, output: StrategistOutput) -> None:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold")
        table.add_column("Value")
        table.add_row("Type", output.issue_type)
        table.add_row("Severity", output.severity)
        table.add_row("Priority", output.priority)
        table.add_row("Confidence", output.confidence_level)
        table.add_row("Summary", output.issue_summary)

        if output.qiskit_context:
            qc = output.qiskit_context
            table.add_row("Modules", ", ".join(qc.affected_modules) or "—")
            table.add_row("Concepts", ", ".join(qc.domain_concepts) or "—")
            table.add_row("Rust Layer", "Yes" if qc.is_rust_layer else "No")
            table.add_row("User Error", "Yes" if qc.is_user_error else "No")
            table.add_row(
                "Quantum Math",
                "Sensitive" if qc.quantum_math_sensitivity else "No",
            )

        console.print(table)

    def _print_architect_summary(self, output) -> None:
        console.print(f"  Plan: {output.plan_summary[:120]}")
        console.print(f"  Localized files: {len(output.localized_files)}")
        for loc in output.localized_files[:5]:
            console.print(f"    • {loc.file_path} — {loc.reason[:80]}")
        console.print(f"  Steps: {len(output.implementation_steps)}")
        for step in output.implementation_steps:
            console.print(
                f"    {step.step_number}. [{step.action}] {step.description[:80]}"
            )
        if output.cross_module_impacts:
            console.print("  ⚠️ Cross-module impacts:")
            for imp in output.cross_module_impacts:
                console.print(f"    • {imp[:80]}")

    def _print_developer_summary(self, output) -> None:
        console.print(f"  Changes: {len(output.changes)} files")
        for change in output.changes:
            console.print(
                f"    • {change.file_path} — {change.change_description[:60]}"
            )
        console.print(f"  Explanation: {output.explanation[:150]}")
        console.print(f"  Confidence: {output.confidence_level}")

    def _print_validator_summary(self, output) -> None:
        passed = sum(1 for t in output.test_results if t.passed)
        total = len(output.test_results)
        status = "[green]PASS[/green]" if output.all_tests_passed else "[red]FAIL[/red]"
        console.print(f"  Tests: {passed}/{total} passed — {status}")

        if output.regression_detected:
            console.print("  [red]⚠️ REGRESSION DETECTED[/red]")
        if output.quantum_precision_issues:
            for issue in output.quantum_precision_issues:
                console.print(f"  [yellow]⚡ {issue}[/yellow]")
        if output.new_tests_written:
            console.print(f"  New tests written: {len(output.new_tests_written)}")
        if output.feedback_for_developer:
            console.print(
                f"  Feedback: {output.feedback_for_developer[:120]}"
            )

    def _print_final_report(self, pipeline: PipelineRun) -> None:
        duration = ""
        if pipeline.started_at and pipeline.completed_at:
            delta = pipeline.completed_at - pipeline.started_at
            duration = f" in {delta.total_seconds():.1f}s"

        console.print()
        console.print(Panel(
            f"[bold green]Pipeline completed{duration}[/bold green]\n\n"
            f"Status:      {pipeline.status.value}\n"
            f"Iterations:  {pipeline.repair_iterations}\n"
            f"Patch size:  {len(pipeline.final_patch)} bytes\n"
            f"Errors:      {len(pipeline.error_log)}",
            title="📋 Final Report",
            border_style="green",
        ))

        if pipeline.final_patch:
            console.print("\n[bold]Generated Patch:[/bold]")
            console.print(
                Panel(
                    pipeline.final_patch[:3000]
                    + ("\n..." if len(pipeline.final_patch) > 3000 else ""),
                    title="Unified Diff",
                    border_style="dim",
                )
            )
