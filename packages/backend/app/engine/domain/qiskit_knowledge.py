"""
Qiskit Domain Knowledge Base.

This module provides structured, domain-specific knowledge about the Qiskit
repository that agents use to make better decisions.  It encodes the kind of
"tribal knowledge" a senior Qiskit contributor would have:

  * Which directories map to which subsystems.
  * Which changes are high-risk (e.g., touching the transpiler basis set).
  * How to distinguish a user error from a library bug.
  * Floating-point tolerance thresholds for quantum-state comparisons.
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────────────
# 1. Repository Map – directory → description & risk notes
# ──────────────────────────────────────────────────────────────────────────────

QISKIT_REPO = "Qiskit/qiskit"
QISKIT_LANGUAGE = "Python"

QISKIT_MODULE_MAP: dict[str, dict[str, str]] = {
    "qiskit/circuit": {
        "description": (
            "Core quantum circuit representation. Contains QuantumCircuit, "
            "QuantumRegister, ClassicalRegister, and the full standard gate library."
        ),
        "risk": "HIGH – almost every part of Qiskit depends on circuit definitions.",
        "key_files": (
            "quantumcircuit.py, gate.py, instruction.py, library/standard_gates/, "
            "parameterexpression.py, parametervector.py"
        ),
    },
    "qiskit/transpiler": {
        "description": (
            "Transpilation pipeline that converts abstract circuits into "
            "hardware-executable circuits.  Contains analysis, optimization, "
            "routing and scheduling passes."
        ),
        "risk": (
            "CRITICAL – the transpiler pass manager orchestrates dozens of "
            "interdependent passes. Changing one pass can cascade."
        ),
        "key_files": (
            "passmanager.py, preset_passmanagers/, passes/optimization/, "
            "passes/routing/, passes/layout/, passes/basis/, target.py"
        ),
    },
    "qiskit/providers": {
        "description": (
            "Backend abstraction.  Defines BackendV2, the Target model, "
            "and provider-specific implementations (BasicSimulator, etc.)."
        ),
        "risk": "MEDIUM – changes here affect which gates/qubits a backend supports.",
        "key_files": "backend.py, provider.py, basic_provider/",
    },
    "qiskit/quantum_info": {
        "description": (
            "Quantum information utilities: Operator, Statevector, DensityMatrix, "
            "partial_trace, state_fidelity, process fidelity."
        ),
        "risk": (
            "MEDIUM-HIGH – floating-point precision is critical. "
            "Tests must use `np.allclose` or `assertAlmostEqual`."
        ),
        "key_files": (
            "operators/operator.py, states/statevector.py, states/densitymatrix.py"
        ),
    },
    "qiskit/dagcircuit": {
        "description": (
            "DAG (Directed Acyclic Graph) representation of circuits. "
            "The transpiler works on DAGCircuit internally."
        ),
        "risk": "HIGH – structural changes here break transpiler passes.",
        "key_files": "dagcircuit.py, dagnode.py, dagdependency.py",
    },
    "qiskit/synthesis": {
        "description": (
            "Unitary synthesis and circuit decomposition algorithms "
            "(one_qubit_decompose, two_qubit_decompose, Solovay-Kitaev, etc.)."
        ),
        "risk": "HIGH – mathematical correctness is non-negotiable.",
        "key_files": (
            "one_qubit_decompose.py, two_qubit_decompose.py, "
            "qft_decompose.py, linear_phase/"
        ),
    },
    "qiskit/passmanager": {
        "description": (
            "Generic pass-manager framework (not transpiler-specific). "
            "Controls the flow of passes, property sets, and logging."
        ),
        "risk": "MEDIUM – framework changes affect all pass-manager users.",
        "key_files": "passmanager.py, flow_controllers.py",
    },
    "qiskit/primitives": {
        "description": (
            "Sampler and Estimator primitives for executing circuits "
            "and computing expectation values (V1 and V2 interfaces)."
        ),
        "risk": "MEDIUM – public API for all runtime execution.",
        "key_files": "statevector_sampler.py, statevector_estimator.py",
    },
    "qiskit/pulse": {
        "description": (
            "Pulse-level control: schedule, instructions, channels. "
            "Used for fine-grained hardware control."
        ),
        "risk": "LOW-MEDIUM – relatively isolated subsystem.",
        "key_files": "schedule.py, instructions/, channels.py, library/",
    },
    "qiskit/compiler": {
        "description": (
            "High-level compilation entry points: transpile(), assemble(), "
            "schedule() functions."
        ),
        "risk": (
            "MEDIUM – thin wrappers, but API surface used by every Qiskit user."
        ),
        "key_files": "transpiler.py, assembler.py, scheduler.py",
    },
    "qiskit/visualization": {
        "description": "Circuit and data visualization (matplotlib, text, latex).",
        "risk": "LOW – visual-only, no computational impact.",
        "key_files": "circuit/matplotlib.py, circuit/text.py, counts_visualization.py",
    },
    "qiskit/qasm": {
        "description": "OpenQASM 2 / 3 import and export.",
        "risk": "MEDIUM – compatibility with the QASM standard is important.",
        "key_files": "qasm2/, qasm3/",
    },
    "crates/": {
        "description": (
            "Rust accelerated modules compiled via PyO3.  Includes "
            "circuit, synthesis, and transpiler speedups."
        ),
        "risk": (
            "HIGH – Rust changes require recompilation and careful "
            "Python↔Rust boundary testing."
        ),
        "key_files": "accelerate/src/, circuit/src/, qasm2/src/",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# 2. Gate & Instruction Taxonomy
# ──────────────────────────────────────────────────────────────────────────────

STANDARD_GATES = {
    "single_qubit": [
        "HGate", "XGate", "YGate", "ZGate", "SGate", "SdgGate",
        "TGate", "TdgGate", "RXGate", "RYGate", "RZGate",
        "U1Gate", "U2Gate", "U3Gate", "UGate", "PhaseGate",
        "SXGate", "SXdgGate", "IGate",
    ],
    "two_qubit": [
        "CXGate", "CZGate", "CYGate", "SwapGate", "iSwapGate",
        "ECRGate", "RZXGate", "RZZGate", "RXXGate", "RYYGate",
        "CPhaseGate", "CSGate", "CSdgGate", "CSXGate",
        "CHGate", "CRXGate", "CRYGate", "CRZGate",
    ],
    "three_qubit": [
        "CCXGate", "CCZGate", "CSwapGate",
    ],
    "multi_qubit": [
        "MCXGate", "MCPhaseGate",
    ],
}

GATE_VS_INSTRUCTION = """
In Qiskit, a Gate is a special type of Instruction:
  • Instruction: any operation (including measurements, resets, barriers).
  • Gate: a unitary operation on qubits only (no classical bits).
  • ControlledGate: a Gate that is conditional on control qubits.

When modifying gate definitions, always check:
  1. Is the matrix/unitary correct?
  2. Is the inverse (`.inverse()`) updated?
  3. Is the decomposition (`.definition`) consistent?
  4. Is it registered in the standard-gate library and basis sets?
"""

# ──────────────────────────────────────────────────────────────────────────────
# 3. Transpilation Pipeline Knowledge
# ──────────────────────────────────────────────────────────────────────────────

TRANSPILER_PASS_CATEGORIES = {
    "analysis": {
        "description": "Read-only passes that collect information (e.g., DAGLongestPath, CountOps).",
        "examples": ["CountOps", "Depth", "NumTensorFactors", "DAGLongestPath"],
    },
    "transformation": {
        "description": "Modify the circuit (e.g., Optimize1qGates, CXCancellation).",
        "examples": [
            "Optimize1qGates", "Optimize1qGatesDecomposition",
            "CXCancellation", "CommutativeCancellation",
            "RemoveBarriers", "RemoveResetInZeroState",
        ],
    },
    "routing": {
        "description": (
            "Map logical qubits to physical qubits on a device topology "
            "(e.g., SabreSwap, StochasticSwap)."
        ),
        "examples": ["SabreSwap", "StochasticSwap", "BasicSwap", "LookaheadSwap"],
    },
    "layout": {
        "description": "Initial qubit placement (e.g., SabreLayout, TrivialLayout).",
        "examples": [
            "SabreLayout", "TrivialLayout", "DenseLayout",
            "NoiseAdaptiveLayout", "SetLayout",
        ],
    },
    "scheduling": {
        "description": (
            "Add timing constraints for hardware execution "
            "(e.g., ALAPSchedule, PadDynamicalDecoupling)."
        ),
        "examples": [
            "ALAPScheduleAnalysis", "ASAPScheduleAnalysis",
            "PadDynamicalDecoupling", "ConstrainedReschedule",
        ],
    },
    "basis_change": {
        "description": (
            "Translate gates to a target basis set "
            "(e.g., BasisTranslator, UnrollCustomDefinitions)."
        ),
        "examples": [
            "BasisTranslator", "UnrollCustomDefinitions",
            "Unroll3qOrMore", "Decompose",
        ],
    },
}

TRANSPILER_PRESET_LEVELS = """
Qiskit's `transpile()` has optimization levels 0-3:
  • Level 0: No optimization (just basis translation + routing).
  • Level 1: Light optimization (1q gate merging, 2q gate cancellation).
  • Level 2: Moderate optimization (commutation analysis, noise-aware layout).
  • Level 3: Heavy optimization (unitary KAK decomposition, resynthesis).

When a bug affects transpilation, always test across ALL optimization levels.
"""

# ──────────────────────────────────────────────────────────────────────────────
# 4. Common Bug Patterns in Qiskit
# ──────────────────────────────────────────────────────────────────────────────

COMMON_BUG_PATTERNS = [
    {
        "pattern": "Gate decomposition inconsistency",
        "description": (
            "The `.definition` property of a gate decomposes into gates that "
            "are not equivalent to the original unitary."
        ),
        "affected_modules": ["qiskit/circuit", "qiskit/synthesis"],
        "detection": "Compare Operator(gate) vs Operator(gate.definition).",
    },
    {
        "pattern": "Parameter binding failure",
        "description": (
            "ParameterExpression or ParameterVector fails to bind correctly, "
            "causing `CircuitError` or wrong numerical values."
        ),
        "affected_modules": ["qiskit/circuit"],
        "detection": "Check `.bind_parameters()` and `.assign_parameters()` output.",
    },
    {
        "pattern": "Transpiler pass ordering regression",
        "description": (
            "A pass that was previously run before another is now run after, "
            "causing the circuit to be malformed."
        ),
        "affected_modules": ["qiskit/transpiler"],
        "detection": "Trace the preset pass manager and compare pass order.",
    },
    {
        "pattern": "Backend Target mismatch",
        "description": (
            "The Target object reports a gate as available, but the backend "
            "rejects it at execution time (or vice versa)."
        ),
        "affected_modules": ["qiskit/providers", "qiskit/transpiler"],
        "detection": "Compare Target.operation_names with actual backend acceptance.",
    },
    {
        "pattern": "Floating-point unitarity violation",
        "description": (
            "A synthesized unitary matrix is not actually unitary due to "
            "accumulated floating-point error."
        ),
        "affected_modules": ["qiskit/quantum_info", "qiskit/synthesis"],
        "detection": "Check U @ U† ≈ I with tolerance ~1e-10.",
    },
    {
        "pattern": "DAGCircuit ↔ QuantumCircuit round-trip loss",
        "description": (
            "Converting QuantumCircuit → DAGCircuit → QuantumCircuit loses "
            "metadata (conditions, labels, calibrations)."
        ),
        "affected_modules": ["qiskit/dagcircuit", "qiskit/circuit"],
        "detection": "Assert deep equality before/after round-trip.",
    },
    {
        "pattern": "Rust-Python boundary data corruption",
        "description": (
            "Data passed between the Python layer and the Rust accelerator "
            "(via PyO3) is silently truncated or mistyped."
        ),
        "affected_modules": ["crates/", "qiskit/circuit"],
        "detection": "Compare Python-only vs Rust-accelerated results.",
    },
    {
        "pattern": "QASM import/export fidelity loss",
        "description": (
            "Exporting a circuit to OpenQASM and re-importing it produces "
            "a different circuit (missing custom gates, wrong angles)."
        ),
        "affected_modules": ["qiskit/qasm"],
        "detection": "Round-trip QASM export → import and compare Operators.",
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# 5. User-Error vs Library-Bug Heuristics
# ──────────────────────────────────────────────────────────────────────────────

USER_ERROR_SIGNALS = [
    "The reporter uses deprecated API (e.g., `execute()` instead of Sampler/Estimator).",
    "The error is `CircuitError: 'not enough qubits'` — usually wrong qubit count.",
    "The reporter confuses gate ordering (big-endian vs little-endian qubit labelling).",
    "The issue mentions 'I upgraded Qiskit and my code broke' without checking migration guide.",
    "The traceback originates entirely in user code, not in `qiskit/` internals.",
    "The reporter expects Aer or IBMQ features that were split into separate packages.",
]

LIBRARY_BUG_SIGNALS = [
    "The traceback originates inside `qiskit/` source code.",
    "Multiple independent users report the same error.",
    "The error occurs in a regression test that previously passed.",
    "The problem is in transpiler output for a valid circuit.",
    "The error disappears at a different optimization level.",
    "A Qiskit maintainer has confirmed the issue.",
    "Git bisect points to a specific commit introducing the problem.",
]

# ──────────────────────────────────────────────────────────────────────────────
# 6. Floating-Point Tolerance Constants
# ──────────────────────────────────────────────────────────────────────────────

QUANTUM_PRECISION = {
    "atol": 1e-10,
    "rtol": 1e-7,
    "description": (
        "Default tolerances for quantum-state and unitary comparisons. "
        "Tighter than numpy defaults because quantum computing is "
        "sensitive to phase errors."
    ),
    "note": (
        "For Statevector.equiv(), the global phase is ignored. "
        "For Operator equality, use Operator.equiv() which ignores global phase, "
        "or == which does not."
    ),
}

# ──────────────────────────────────────────────────────────────────────────────
# 7. Testing Conventions
# ──────────────────────────────────────────────────────────────────────────────

TESTING_CONVENTIONS = {
    "framework": "pytest (previously unittest, migration ongoing)",
    "test_directory": "test/",
    "test_naming": "test/python/test_<module>.py or test/python/<subpackage>/test_*.py",
    "key_test_targets": [
        "test/python/circuit/",
        "test/python/transpiler/",
        "test/python/quantum_info/",
        "test/python/compiler/",
        "test/python/dagcircuit/",
        "test/python/providers/",
        "test/python/synthesis/",
        "test/python/primitives/",
    ],
    "run_command": "python -m pytest test/python/<path> -x -v",
    "tox_command": "tox -e py",
    "coverage_command": "python -m pytest --cov=qiskit test/",
    "tolerance_note": (
        "Many quantum tests use `self.assertAlmostEqual` or `numpy.allclose` "
        "with specific atol/rtol values. Never tighten tolerances without "
        "domain justification."
    ),
}
