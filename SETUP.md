# 🛠️ SWE-Agent Setup Guide

This guide covers setting up the **SWE-Agent Chrome Copilot** for local development, Docker, and Kubernetes.

---

## 📋 Prerequisites

- **Python 3.12+**
- **Node.js 18+** (for Extension building if needed)
- **Docker & Docker Compose**
- **Git**
- **Google Gemini API Key** ([Get one here](https://aistudio.google.com/apikey))
- **GitHub Token** (Classic or Fine-grained with `repo` scope)

---

## 🚀 1. Local Development

### Backend Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-org/swe-agent-copilot.git
   cd swe-agent-copilot
   ```

2. **Navigate to backend:**
   ```bash
   cd packages/backend
   ```

3. **Create virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY and GITHUB_TOKEN
   ```

6. **Run the Server:**
   ```bash
   python main.py
   # Server starts at http://localhost:8000
   ```

### Chrome Extension Setup

1. Open Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in top right).
3. Click **Load unpacked**.
4. Select the `packages/extension` folder.
5. The **SWE-Agent Copilot** icon should appear in your toolbar.

---

## 🐳 2. Docker Setup

Run the entire stack (Backend + optional Redis) using Docker Compose.

1. **Configure Environment:**
   ensure `packages/backend/.env` is set up.

2. **Start Services:**
   ```bash
   # Development mode (hot-reload)
   docker compose up

   # Production mode
   docker compose --profile prod up -d
   ```

3. **Verify:**
   - API: `http://localhost:8000/docs`
   - Health: `http://localhost:8000/health`

---

## ☸️ 3. Kubernetes Deployment

Deploy to a K8s cluster (EKS, GKE, or Minikube).

1. **Encode Secrets:**
   ```bash
   echo -n "your-gemini-key" | base64
   echo -n "your-github-token" | base64
   ```

2. **Update Manifest:**
   Edit `k8s/deployment.yaml` and replace the placeholder values in the `Secret` section.

3. **Deploy:**
   ```bash
   kubectl apply -f k8s/deployment.yaml
   ```

4. **Check Status:**
   ```bash
   kubectl get pods -n swe-agent
   kubectl get svc -n swe-agent
   ```

---

## 🧪 Running Tests

Ensure your environment is robust.

```bash
# From packages/backend
pytest tests/
```
