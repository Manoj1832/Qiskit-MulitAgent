# 🏆 SWE-bench Performance & Methodology

**SWE-bench** is a rigorous evaluation framework for Large Language Models (LLMs) on real-world software engineering tasks.

---

## 📊 Overview

SWE-bench consists of **2,294 task instances** collected from 12 popular Python repositories (e.g., `django`, `scikit-learn`, `flask`). Each instance includes:
1. **GitHub Issue**: Problem description.
2. **Pull Request**: The human-written solution (Gold Standard).
3. **Tests**: Verify the fix (Fail-to-Pass).

### Current State of the Art (SOTA)
- **Top Models**: GPT-4, Claude 3 Opus.
- **Top Agents**: SWE-agent (Princeton), Devin.
- **Pass Rates**: ~12-20% on full dataset (extremely hard).

---

## 🎯 Our System Approach

**SWE-Agent Chrome Copilot** tackles these benchmarks using a hierarchical agent pipeline (`Sentry` → `Strategist` → `Architect` → `Developer` → `Validator`).

### Key Strategies for High Performance
1. **RAG Context Retrieval**: Instead of stuffing the whole codebase into context, we use vector search (FAISS) to find relevant snippets.
2. **Multi-Step Reasoning**:
   - **Sentry**: Filters noise from issue descriptions.
   - **Strategist**: Breaks complex tasks into sub-problems.
   - **Architect**: Maps dependencies to avoid "hallucinated imports".
3. **Self-Correction (Validator Loop)**:
   - The Validator runs tests *before* submitting. If they fail, the Developer gets 3 chances to fix the code. This mimics a human "Red-Green-Refactor" cycle.

---

## 🛠️ Running Benchmarks Locally

To evaluate our system against a specific SWE-bench instance:

### 1. Prerequisite
Ensure you have the environment set up (see [SETUP.md](./SETUP.md)).
```bash
# Install test dependencies
cd packages/backend
pip install pytest pytest-cov
```

### 2. Run Single Instance Evaluation
We provide a script to run the agent against a specific issue ID.

```bash
# Example: Run agent on Qiskit issue #12345
export GEMINI_API_KEY=your_key
python -m app.engine.benchmark_runner --repo Qiskit/qiskit --issue 12345
```

### 3. Full Benchmark Suite (Docker) - *Coming Soon*
Running the full SWE-bench requires significant compute. We are preparing a Dockerized harness to run evaluations in parallel.

---

## 📈 Metric Definitions

| Metric | Definition | Target |
| :--- | :--- | :--- |
| **Pass Rate** | % of issues where all tests pass. | > 25% |
| **Context Window** | Avg tokens used per issue. | < 50k |
| **Correction Loops** | Avg attempts by Validator. | < 1.5 |
| **Cost** | Avg API cost per issue. | < $0.50 |

---

## 🔗 Resources
- [Official SWE-bench Paper](https://arxiv.org/abs/2310.06770)
- [Leaderboard](https://www.swebench.com/)
