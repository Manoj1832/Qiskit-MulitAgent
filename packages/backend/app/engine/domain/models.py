"""
Pydantic models shared across ALL agents in the multi-agent pipeline.

Every model here represents a well-defined *contract* between agents.
The Orchestrator uses these to validate data flowing through the pipeline.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# Enumerations – constrained vocabularies for consistent agent communication
# ──────────────────────────────────────────────────────────────────────────────

class IssueType(str, Enum):
    BUG = "Bug"
    FEATURE_REQUEST = "Feature Request"
    PERFORMANCE = "Performance"
    REFACTOR = "Refactor"
    DOCUMENTATION = "Documentation"
    TEST_FAILURE = "Test Failure"
    DEPRECATION = "Deprecation"
    QUANTUM_CORRECTNESS = "Quantum Correctness"  # Qiskit-specific


class Severity(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Confidence(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class PipelineStatus(str, Enum):
    """Status of the overall pipeline run."""
    PENDING = "pending"
    TRIAGE = "triage"
    PLANNING = "planning"
    CODING = "coding"
    VALIDATING = "validating"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentName(str, Enum):
    """Canonical agent names used across the framework."""
    ORCHESTRATOR = "Orchestrator"
    SENTRY = "Sentry"
    STRATEGIST = "Strategist"
    ARCHITECT = "Architect"
    DEVELOPER = "Developer"
    VALIDATOR = "Validator"


# ──────────────────────────────────────────────────────────────────────────────
# Qiskit-Specific Domain Types
# ──────────────────────────────────────────────────────────────────────────────

class QiskitModule(str, Enum):
    """Top-level Qiskit modules for targeted file search."""
    CIRCUIT = "qiskit.circuit"
    TRANSPILER = "qiskit.transpiler"
    PROVIDERS = "qiskit.providers"
    QUANTUM_INFO = "qiskit.quantum_info"
    DAGCIRCUIT = "qiskit.dagcircuit"
    SYNTHESIS = "qiskit.synthesis"
    PASSMANAGER = "qiskit.passmanager"
    PRIMITIVES = "qiskit.primitives"
    PULSE = "qiskit.pulse"
    COMPILER = "qiskit.compiler"
    RESULT = "qiskit.result"
    VISUALIZATION = "qiskit.visualization"
    QASM = "qiskit.qasm"
    UTILS = "qiskit.utils"
    # Rust-accelerated internals
    ACCELERATE = "_accelerate"


class QiskitDomainConcept(str, Enum):
    """High-level quantum computing concepts relevant during triage."""
    GATE_DEFINITION = "Gate Definition"
    CIRCUIT_CONSTRUCTION = "Circuit Construction"
    TRANSPILATION_PASS = "Transpilation Pass"
    QUBIT_MAPPING = "Qubit Mapping"
    BASIS_GATE_SET = "Basis Gate Set"
    UNITARY_SYNTHESIS = "Unitary Synthesis"
    NOISE_MODEL = "Noise Model"
    QUANTUM_STATE = "Quantum State"
    ENTANGLEMENT = "Entanglement"
    MEASUREMENT = "Measurement"
    PARAMETERIZED_CIRCUIT = "Parameterized Circuit"
    PULSE_SCHEDULE = "Pulse Schedule"
    BACKEND_CONFIGURATION = "Backend Configuration"
    OBSERVABLE = "Observable"
    OPERATOR = "Operator"


# ──────────────────────────────────────────────────────────────────────────────
# Shared Data Models – the pipeline "messages"
# ──────────────────────────────────────────────────────────────────────────────

class GitHubIssueData(BaseModel):
    """Raw GitHub issue data fetched by the Sentry."""
    repo: str = Field(..., description="owner/repo")
    issue_number: int
    title: str
    body: str = ""
    labels: list[str] = Field(default_factory=list)
    state: str = "open"
    author: str = ""
    created_at: Optional[str] = None
    comments: list[str] = Field(default_factory=list)
    linked_pr_numbers: list[int] = Field(default_factory=list)
    linked_pr_files: list[str] = Field(default_factory=list)
    milestone: Optional[str] = None


class TechnicalClues(BaseModel):
    """Technical signals extracted from the issue text."""
    error_messages: list[str] = Field(default_factory=list)
    mentioned_files: list[str] = Field(default_factory=list)
    mentioned_functions: list[str] = Field(default_factory=list)
    mentioned_classes: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    stack_trace: Optional[str] = None


class QiskitContext(BaseModel):
    """Qiskit-specific context detected by the Strategist."""
    affected_modules: list[str] = Field(
        default_factory=list,
        description="e.g. ['qiskit.circuit', 'qiskit.transpiler']",
    )
    domain_concepts: list[str] = Field(
        default_factory=list,
        description="e.g. ['Gate Definition', 'Transpilation Pass']",
    )
    is_rust_layer: bool = Field(
        default=False,
        description="True if the bug likely involves the Rust accelerator",
    )
    is_user_error: bool = Field(
        default=False,
        description="True if the agent believes this is user misunderstanding, not a library bug",
    )
    quantum_math_sensitivity: bool = Field(
        default=False,
        description="True if fix involves floating-point quantum math (unitary matrices, angles)",
    )
    backwards_compatibility_risk: bool = Field(
        default=False,
        description="True if the fix could break the public API contract",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Agent Output Models (one per agent)
# ──────────────────────────────────────────────────────────────────────────────

class StrategistOutput(BaseModel):
    """Output of the Strategist (Issue Analyst) agent."""
    issue_summary: str
    issue_type: str
    severity: str
    priority: str
    expected_behavior: str
    actual_behavior: str
    reproduction_steps: list[str] = Field(default_factory=list)
    technical_clues: TechnicalClues = Field(default_factory=TechnicalClues)
    qiskit_context: QiskitContext = Field(default_factory=QiskitContext)
    suspected_components: list[str] = Field(default_factory=list)
    confidence_level: str = "Medium"
    recommended_next_agent: str = "Architect"


class FileLocation(BaseModel):
    """A specific location in the codebase identified during planning."""
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    reason: str = ""
    language: str = "python"


class PlanStep(BaseModel):
    """A single step in the Architect's implementation plan."""
    step_number: int
    description: str
    target_files: list[str] = Field(default_factory=list)
    action: str = Field(
        ..., description="CREATE | MODIFY | DELETE | TEST"
    )
    rationale: str = ""
    cross_file_dependencies: list[str] = Field(
        default_factory=list,
        description="Other files that must stay consistent with this change",
    )
    risk_notes: str = ""


class ArchitectOutput(BaseModel):
    """Output of the Architect (Planner) agent."""
    plan_summary: str
    localized_files: list[FileLocation] = Field(default_factory=list)
    implementation_steps: list[PlanStep] = Field(default_factory=list)
    affected_test_files: list[str] = Field(default_factory=list)
    cross_module_impacts: list[str] = Field(
        default_factory=list,
        description=(
            "Warnings like 'changing gate def in library requires updating "
            "transpiler basis_set logic'"
        ),
    )
    estimated_complexity: str = "Medium"
    confidence_level: str = "Medium"


class CodeChange(BaseModel):
    """A single file-level code change produced by the Developer."""
    file_path: str
    original_content: str = ""
    modified_content: str = ""
    diff_patch: str = ""
    change_description: str = ""
    language: str = "python"


class DeveloperOutput(BaseModel):
    """Output of the Developer (Code Gen) agent."""
    changes: list[CodeChange] = Field(default_factory=list)
    explanation: str = ""
    new_files_created: list[str] = Field(default_factory=list)
    files_deleted: list[str] = Field(default_factory=list)
    combined_patch: str = Field(
        default="",
        description="Unified diff of all changes",
    )
    iteration: int = Field(default=1, description="Repair loop iteration count")
    confidence_level: str = "Medium"


class TestResult(BaseModel):
    """Result of a single test execution."""
    test_name: str
    passed: bool
    error_message: str = ""
    traceback: str = ""
    duration_seconds: float = 0.0


class ValidatorOutput(BaseModel):
    """Output of the Validator (Tester) agent."""
    all_tests_passed: bool = False
    test_results: list[TestResult] = Field(default_factory=list)
    new_tests_written: list[str] = Field(default_factory=list)
    regression_detected: bool = False
    quantum_precision_issues: list[str] = Field(
        default_factory=list,
        description="Warnings about floating-point differences in quantum state comparisons",
    )
    feedback_for_developer: str = ""
    iteration: int = 1


class SentryOutput(BaseModel):
    """Output of the Sentry (Git/PR Reviewer) agent."""
    issue_data: Optional[GitHubIssueData] = None
    repo_structure: list[str] = Field(
        default_factory=list,
        description="Key directories and files discovered in the repo",
    )
    related_issues: list[int] = Field(
        default_factory=list,
        description="Other issue numbers that look related",
    )
    related_prs: list[int] = Field(default_factory=list)
    recent_commits_summary: str = ""
    pr_review_comments: str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline Run Record
# ──────────────────────────────────────────────────────────────────────────────

class PipelineRun(BaseModel):
    """Full record of a single pipeline execution."""
    run_id: str
    repo: str
    issue_number: int
    status: PipelineStatus = PipelineStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Agent outputs (filled as the pipeline progresses)
    sentry_output: Optional[SentryOutput] = None
    strategist_output: Optional[StrategistOutput] = None
    architect_output: Optional[ArchitectOutput] = None
    developer_output: Optional[DeveloperOutput] = None
    validator_output: Optional[ValidatorOutput] = None

    # Repair loop
    repair_iterations: int = 0
    max_repair_iterations: int = 3

    # Final artefact
    final_patch: str = ""
    error_log: list[str] = Field(default_factory=list)
