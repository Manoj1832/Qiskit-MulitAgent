# 🔄 SWE-Agent Workflow

This document outlines the **SWE-Agent Chrome Copilot** development and operational workflow, explaining how issues flow through the agents and how developers interact with the system.

---

## 🛠️ Development Cycle

1. **Issue Creation**:
   - A user notices a bug or feature request on GitHub.
   - They create an **Issue** with a descriptive title and body.

2. **Agent Trigger**:
   - Depending on configuration, the **Sentry Agent** (Analysis & Planning) is triggered:
     - Automatically via GitHub Webhook (Enterprise Setup)
     - Manually via `/analyze` slash command in a comment
     - Manually via Chrome Extension popup button

3. **Analysis Phase (Sentry)**:
   - **Step**: Fetches issue details, linked PRs, and repository context.
   - **Output**: 
     - Summary of the problem.
     - Identification of relevant files.
     - Initial implementation plan (if requested).

4. **Coding Phase (Developer)**:
   - **Step**: Based on the plan, the **Developer Agent** (LLM) generates code changes.
   - **Output**: 
     - A diff/patch file.
     - Commit message suggestion.

5. **Validation Phase (Validator)**:
   - **Step**: The **Validator Agent** runs linting and basic tests on the proposed patch.
   - **Loop**: If validation fails, it feeds errors back to the **Developer Agent** for up to 3 repair iterations.

6. **Review & Merge**:
   - Once validated, a **Pull Request** is created.
   - The user reviews the PR using the **PR Reviewer Tool** (`/review`).

---

## 🤖 PR-Agent Interactions

Integration of PR-Agent capabilities within the workflow.

### 1. **Code Review (`/review`)**
   - **Trigger**: New PR or `/review` command.
   - **Flow**:
     - Agent fetches PR diff.
     - Parses changes and context.
     - Evaluates code quality, security, and complexity.
     - Posts structured review comment.

### 2. **Code Improvement (`/improve`)**
   - **Trigger**: `/improve` command.
   - **Flow**:
     - Agent analyzes diff chunks.
     - Suggests inline code improvements (performance, readability).
     - Provides copy-paste ready code blocks.

### 3. **Test Generation (`/test`)**
   - **Trigger**: `/test` command.
   - **Flow**:
     - Agent scans new logic in diff.
     - Generates unit/integration tests using the project's framework (pytest/unittest).
     - Provides complete test file content.

---

## 🚀 CI/CD Pipeline

Automated workflows defined in `.github/workflows/`.

1. **Lint & Test**: On push to `main` or PR.
   - Runs `ruff` for linting.
   - Runs `pytest` suite.
2. **Docker Build**:
   - Builds multi-stage Docker image.
   - Pushes to container registry (GHCR/DockerHub).
3. **Deployment**:
   - Deploys new image to Kubernetes cluster.
   - Updates `image:tag` in `deployment.yaml`.
