# 🤝 Contributing Guide

Thank you for your interest in contributing to the **SWE-Agent Chrome Copilot** project!

This document outlines the process for contributing code, reporting bugs, and proposing new features.

---

## 🚀 Getting Started

1. **Fork the repository** on GitHub.
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/swe-agent-copilot.git
   cd swe-agent-copilot
   ```
3. **Set up the environment**:
   - Follow instructions in [SETUP.md](./SETUP.md).
   - Install pre-commit hooks (if configured).

---

## 🛠️ Development Workflow

1. **Create a branch**:
   ```bash
   git checkout -b feature/my-cool-feature
   ```
2. **Make changes**:
   - Follow the existing code style (PEP 8 for Python).
   - Write meaningful commit messages.
   - Add tests for new features.
3. **Run tests**:
   ```bash
   pytest packages/backend/tests
   ```
4. **Lint your code**:
   ```bash
   ruff check packages/backend
   ```

---

## 🐛 Reporting Bugs

Open an issue on GitHub using the **Bug Report** template. Include:
- Description of the issue.
- Steps to reproduce.
- Expected vs. actual behavior.
- Screenshots or logs.

---

## 💡 Feature Requests

Open an issue using the **Feature Request** template. Describe:
- The problem you want to solve.
- Proposed solution.
- Alternatives considered.

---

## 📝 Pull Request Process

1. **Push your changes** to your fork.
2. **Open a Pull Request** against the `main` branch.
3. **Describe your changes** clearly in the PR description.
4. **Link related issues** (e.g., "Fixes #123").
5. **Wait for review**: A maintainer will review your code. address any feedback.

---

## 📜 Code of Conduct

Please be respectful and inclusive in all interactions. We follow the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
