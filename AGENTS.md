# 🤖 AI Agents & System Architecture

This document details the multi-agent system powering **SWE-Agent Chrome Copilot** and explains how it differs from existing solutions.

---

## 🧠 The 5-Agent Pipeline

Our system uses a specialized team of AI agents, each with a distinct role, mimicking a real-world software engineering team.

### 1. **🔍 Sentry Agent (The Analyst)**
- **Role**: Initial triage and information gathering.
- **Responsibilities**:
  - Fetches Issue details, comments, and linked PRs.
  - Explores the repository structure (file tree).
  - Retrieves relevant context using RAG (Vector Search).
- **Output**: A comprehensive `SentryOutput` report summarizing the problem and key files.

### 2. **🧠 Strategist Agent (The Planner)**
- **Role**: High-level problem solving and strategy.
- **Responsibilities**:
  - Analyzes the Sentry report.
  - Determines the root cause of the issue.
  - Formulates a step-by-step implementation plan.
  - Identifies edge cases and potential pitfalls.
- **Output**: A strategic plan (`StrategyOutput`) for the Architect.

### 3. **📐 Architect Agent (The Designer)**
- **Role**: Technical design and file mapping.
- **Responsibilities**:
  - Translates the strategy into specific file valid/edit actions.
  - Checks for dependencies and import cycles.
  - Ensures architectural consistency with existing code.
- **Output**: A detailed `ArchitectOutput` with file paths and modification intent.

### 4. **💻 Developer Agent (The Coder)**
- **Role**: Writing the actual code.
- **Responsibilities**:
  - Executes the Architect's plan.
  - Generates code patches (using unified diff format).
  - Follows project coding standards (linting, variable naming).
- **Output**: A `Patch` object containing the code changes.

### 5. **✅ Validator Agent (The QA)**
- **Role**: Quality assurance and testing.
- **Responsibilities**:
  - Runs the generated patch against a sandbox environment.
  - Executes linters (Ruff/Flake8) and unit tests (Pytest).
  - If tests fail, it feeds the error log back to the **Developer Agent** for a "Repair Loop" (up to 3 iterations).
- **Output**: A final `PipelineRun` status (Success/Failure) and the verified patch.

---

## 🚀 How We Differ (Innovation)

Unlike standard "Text-to-Code" tools or standalone PR bots, **SWE-Agent Chrome Copilot** combines the best of both worlds:

| Feature | Standard Coding Assistants | PR-Agent (Standalone) | **SWE-Agent Copilot** (Our System) |
| :--- | :--- | :--- | :--- |
| **Workflow** | Single-turn (Chat → Code) | PR Review only | **End-to-End** (Issue → PR → Review) |
| **Context** | Limited (Current file) | Diff context only | **Full Repo RAG** + Diff + Issue Context |
| **Architecture** | Single Model | Single Agent | **Multi-Agent Orchestration** (5 distinct roles) |
| **Interface** | IDE Plugin | GitHub Comment | **Chrome Extension** (Seamless overlay) |
| **Testing** | Manual | None | **Autonomous Test Generation & Validation** |
| **Self-Correction** | ❌ None | ❌ None | ✅ **Validator Agent Loop** (Auto-fixes bugs) |

### Key Differentiator: The "Agency" Loop
Most tools just "spit out code". Our system **thinks, plans, codes, and tests**. If the code fails tests, the Validator Agent catches it and sends it back to the Developer Agent to fix—automatically—before you ever see it.

---

## 🛠️ PR-Agent Tools (The Toolkit)

In addition to the 5-agent pipeline, we integrated specific tools for Pull Requests:

- **Reviewer**: Automated code review with quality scoring.
- **Suggester**: Inline code improvements (performance/security).
- **Test Generator**: Creates test suites for your PRs instantly.

These tools run as "micro-agents" that can be triggered on demand via the Chrome Extension.
