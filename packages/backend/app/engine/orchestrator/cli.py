"""
CLI entry point for the Qiskit SWE-Agent Framework.

Usage examples:

  # Full pipeline for a Qiskit issue
  python -m orchestrator.cli --repo Qiskit/qiskit --issue 12345

  # With verbose logging
  python -m orchestrator.cli --repo Qiskit/qiskit --issue 12345 -v

  # Custom repair iterations
  python -m orchestrator.cli --repo Qiskit/qiskit --issue 12345 --max-iterations 5

  # Save patch to file
  python -m orchestrator.cli --repo Qiskit/qiskit --issue 12345 --output patch.diff

  # Run a single agent (strategist only)
  python -m orchestrator.cli --repo Qiskit/qiskit --issue 12345 --agent strategist
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

# Add the SWE agent root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console

console = Console()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="qiskit-swe-agent",
        description=(
            "Multi-agent SWE framework for Qiskit — "
            "autonomous issue-to-patch pipeline."
        ),
    )

    # Required
    parser.add_argument(
        "--repo",
        type=str,
        default="Qiskit/qiskit",
        help="GitHub repository in owner/name format (default: Qiskit/qiskit)",
    )
    parser.add_argument(
        "--issue",
        type=int,
        required=True,
        help="GitHub issue number to analyze and fix",
    )

    # Pipeline options
    parser.add_argument(
        "--agent",
        type=str,
        choices=["sentry", "strategist", "architect", "developer", "full"],
        default="full",
        help="Run a single agent or the full pipeline (default: full)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Max repair iterations (default: from config or 3)",
    )
    parser.add_argument(
        "--skip-sentry",
        action="store_true",
        help="Skip the Sentry reconnaissance phase",
    )

    # Output
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save the final patch to this file",
    )
    parser.add_argument(
        "--json-output",
        type=str,
        default=None,
        help="Save the full pipeline result as JSON to this file",
    )

    # Debug
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose / debug logging",
    )

    return parser.parse_args()


def _run_single_agent(agent_name: str, repo: str, issue_number: int) -> None:
    """Run a single agent and print its output."""
    from app.engine.utils.github_helper import fetch_issue
    from app.engine.domain.models import GitHubIssueData

    if agent_name == "sentry":
        from app.engine.agents.sentry import SentryAgent
        agent = SentryAgent()
        result = agent.run(repo, issue_number)
        console.print_json(result.model_dump_json(indent=2))

    elif agent_name == "strategist":
        from app.engine.agents.sentry import SentryAgent
        from app.engine.agents.strategist import StrategistAgent

        console.print("[dim]Running Sentry first to gather data…[/dim]")
        sentry = SentryAgent()
        sentry_output = sentry.run(repo, issue_number)

        console.print("[dim]Now running Strategist…[/dim]")
        strategist = StrategistAgent()
        result = strategist.run(
            issue_data=sentry_output.issue_data,
            sentry_output=sentry_output,
        )
        console.print_json(result.model_dump_json(indent=2))

    elif agent_name == "architect":
        from app.engine.agents.sentry import SentryAgent
        from app.engine.agents.strategist import StrategistAgent
        from app.engine.agents.architect import ArchitectAgent

        console.print("[dim]Running Sentry → Strategist → Architect…[/dim]")
        sentry = SentryAgent()
        sentry_output = sentry.run(repo, issue_number)

        strategist = StrategistAgent()
        triage = strategist.run(
            issue_data=sentry_output.issue_data,
            sentry_output=sentry_output,
        )

        architect = ArchitectAgent()
        result = architect.run(
            strategist_output=triage,
            sentry_output=sentry_output,
            repo=repo,
        )
        console.print_json(result.model_dump_json(indent=2))

    elif agent_name == "developer":
        console.print(
            "[yellow]Developer requires full pipeline context. "
            "Use --agent full instead.[/yellow]"
        )
        sys.exit(1)


def main() -> None:
    args = _parse_args()

    # Logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    # Override max iterations if specified
    if args.max_iterations is not None:
        os.environ["MAX_REPAIR_ITERATIONS"] = str(args.max_iterations)

    # Run single agent or full pipeline
    if args.agent != "full":
        _run_single_agent(args.agent, args.repo, args.issue)
        return

    # Full pipeline
    from app.engine.orchestrator.manager import CentralManager

    manager = CentralManager()
    result = manager.run(
        repo=args.repo,
        issue_number=args.issue,
        skip_sentry=args.skip_sentry,
    )

    # Save outputs
    if args.output and result.final_patch:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result.final_patch)
        console.print(f"\n[green]Patch saved to: {args.output}[/green]")

    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))
        console.print(f"[green]Full result saved to: {args.json_output}[/green]")


if __name__ == "__main__":
    main()
