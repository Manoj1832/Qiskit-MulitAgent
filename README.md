# 🤖 SWE-Agent Chrome Copilot

> **Autonomous AI code fixer & PR companion for GitHub**
> 
> Unifies **SWE-Agent** (Issue resolving) and **PR-Agent** (Code Review/Improvement) into a single powerfull Chrome Extension workflow.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)

---

## 🌟 Features

### 🐛 Autonomous Issue Solving
- **Analyzes Issues**: Understands context, linked PRs, and repo structure.
- **Plans & Fixes**: Generates an implementation plan and writes the code patch.
- **Validates**: Runs linters and tests to ensure correctness.

### 👓 Intelligent PR Reviews
- **`/review`**: Comprehensive PR analysis with quality scoring and security checks.
- **`/improve`**: Inline code suggestions to fix bugs and improve performance.
- **`/test`**: Auto-generates unit and integration tests for new changes.

---

## 📚 Documentation

| Guide | Description |
| :--- | :--- |
| **[🚀 Setup Guide](./SETUP.md)** | Installation instructions for Local, Docker, and Kubernetes. |
| **[🎮 Usage Guide](./HOW_TO_USE.md)** | How to use the Extension and Slash Commands. |
| **[🔄 Workflow](./WORKFLOW.md)** | Explanation of the agent pipeline and CI/CD. |
| **[🏗 Architecture](./ARCHITECTURE.md)** | System design and component diagrams. |
| **[📊 Project Status](./PROJECT_STATUS.md)** | Roadmap and module completion tracker. |
| **[🤖 Agents & AI](./AGENTS.md)** | Detailed breakdown of the 5-agent pipeline. |
| **[🏆 Benchmarks](./BENCHMARK.md)** | SWE-bench methodology and performance goals. |
| **[🤝 Contributing](./CONTRIBUTING.md)** | Guidelines for developers. |

---

## ⚡ Quick Start (Docker)

```bash
# 1. Clone & Configure
git clone https://github.com/your-org/swe-agent-copilot.git
cd swe-agent-copilot
cp packages/backend/.env.example packages/backend/.env
# (Edit .env with your GEMINI_API_KEY)

# 2. Run Stack
docker compose up
```

Visit `http://localhost:8000/docs` to see the API is running.

---

## 📂 Repository Structure

```
.
├── packages/
│   ├── backend/           # FastAPI Agents & Tools
│   └── extension/         # Chrome Extension UI
├── k8s/                   # Kubernetes Manifests
├── .github/workflows/     # CI/CD Pipelines
└── docker-compose.yml     # Local orchestration
```

---

## 🛡 Security

- **Tokens**: API keys are managed securely in the backend.
- **Sandboxed**: Agents run in isolated environments.
- **Human-in-the-Loop**: All AI actions (PR creation, comments) require user initiation.