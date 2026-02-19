# 🎮 Usage Guide# this staement is added to create pull request!

This guide explains how to use **SWE-Agent Chrome Copilot** for Issue tracking, PR Review, Code Improvements, and Test Generation.

---

## 🛠️ Chrome Extension UI

The extension provides a powerful interface directly on GitHub pages.

### 1. **Popup Overview**
   - **Dashboard**: See active issues and recent PRs.
   - **Status**: Backend health and LLM model status.
   - **Actions**: Trigger commands without leaving the page.

### 2. **Pull Request Tools**
   Navigate to any Pull Request page to access these tabs:

   - **Review**: Get a complete code review with a quality score (0-100), effort estimate, and key findings.
   - **Improve**: Receive AI-generated code suggestions to enhance performance, readability, or fix bugs.
   - **Test**: Generate a full test suite for the changes in the PR.

---

## ⌨️ Slash Commands

Interact with the agents directly via GitHub comments.

### 1. `/review`
   - **Usage**: Comment `/review` on any Pull Request.
   - **Action**: Triggers a comprehensive PR analysis.
   - **Output**: A detailed comment with:
     - **Quality Score**: Overall rating.
     - **Review Effort**: Estimated time to review (1-5 stars).
     - **Key Issues**: Critical, Major, Minor findings.
     - **Security**: Vulnerability check.

### 2. `/improve`
   - **Usage**: Comment `/improve` on a PR.
   - **Action**: Analyzing the diff for potential code improvements.
   - **Output**:
     - **Code Suggestions**: Before/After code blocks.
     - **Reasoning**: Explanation for each change.
     - **One-Click Apply**: Copy-paste ready snippets.

### 3. **`/test`**
   - **Usage**: Comment `/test` on a PR.
   - **Action**: Generates unit/integration tests based on the diff.
   - **Output**:
     - **Test File**: Complete Python/JS test file content.
     - **Coverage**: Targeting new logic and edge cases.
     - **Framework**: Adapts to project style (pytest, unittest, jest).

### 4. **`/analyze`** (Issues)
   - **Usage**: Comment `/analyze` on an Issue.
   - **Action**: Starts the Sentry Agent to plan a fix.
   - **Output**:
     - **Summary**: Problem statement breakdown.
     - **Plan**: Proposed implementation steps.
     - **Files**: List of files to modify.

---

## ⚙️ Configuration

Customize the agent behavior via `packages/backend/app/settings/configuration.toml` or environment variables.

| Setting | Default | Description |
| :--- | :--- | :--- |
| `model` | `gemini-2.0-flash` | Primary LLM model. |
| `max_model_tokens` | `32000` | Max context window size. |
| `num_max_findings` | `5` | Limit for review issues. |
| `num_code_suggestions_per_chunk` | `4` | Suggestions per diff chunk. |
| `num_tests` | `5` | Number of tests to generate. |
