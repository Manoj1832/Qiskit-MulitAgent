"""
SWE-Agent Chrome Copilot — FastAPI Backend
==========================================

Endpoints:
  POST /token              — Exchange API key for JWT
  GET  /health             — Health check
  POST /analyze-issue      — Analyze a GitHub Issue (SSE streaming)
  POST /analyze-pr         — Analyze a GitHub PR (SSE streaming)
  POST /create-pr          — Auto-create a PR from a generated patch
  POST /review-pr          — PR-Agent style PR review (issues, scoring, security)
  POST /suggest-fixes      — Generate inline code improvement suggestions
  POST /generate-tests     — Auto-generate test suites for changed code
  POST /pr-agent           — Unified PR-Agent command dispatcher

All analysis endpoints stream Server-Sent Events (SSE) so the Chrome
Extension can render each agent phase in real-time.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.core.security import create_access_token, get_current_user, validate_api_key
from app.core.config import ALLOWED_ORIGINS, API_HOST, API_PORT, GITHUB_TOKEN, JWT_EXPIRE_MINUTES
from app.models.schemas import (
    AnalyzeIssueRequest,
    AnalyzePRRequest,
    AnalyzeResponse,
    HealthResponse,
    TokenRequest,
    TokenResponse,
)
from app.services.rag_service import get_rag_memory

# Existing agent orchestrator
from app.engine.orchestrator.manager import CentralManager
from app.engine.domain.models import PipelineRun, PipelineStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("swe_agent.api")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SWE-Agent Chrome Copilot API",
    description="Multi-agent autonomous code fixer for GitHub Issues and PRs",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Chrome extensions need wildcard
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool for running synchronous agent pipeline
_executor = ThreadPoolExecutor(max_workers=4)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _confidence_to_float(level: str) -> float:
    """Convert 'High'/'Medium'/'Low' to a 0-1 float."""
    mapping = {"high": 0.90, "medium": 0.65, "low": 0.40}
    return mapping.get(level.lower(), 0.60)


def _pipeline_to_response(pipeline: PipelineRun, pr_number: int | None = None) -> dict:
    """Convert a PipelineRun to the AnalyzeResponse dict."""
    classification = "unknown"
    root_cause = ""
    confidence = 0.60
    reasoning_steps: list[str] = []
    affected_files: list[str] = []

    if pipeline.strategist_output:
        s = pipeline.strategist_output
        classification = s.issue_type.lower().replace(" ", "-")
        root_cause = s.issue_summary
        confidence = _confidence_to_float(s.confidence_level)
        reasoning_steps.append(f"[Strategist] {s.issue_summary}")
        reasoning_steps.append(f"[Strategist] Severity: {s.severity} | Priority: {s.priority}")

    if pipeline.architect_output:
        a = pipeline.architect_output
        root_cause = a.plan_summary or root_cause
        reasoning_steps.append(f"[Architect] {a.plan_summary[:200]}")
        affected_files = [loc.file_path for loc in a.localized_files]
        confidence = _confidence_to_float(a.confidence_level)

    if pipeline.developer_output:
        d = pipeline.developer_output
        reasoning_steps.append(f"[Developer] {d.explanation[:200]}")
        confidence = _confidence_to_float(d.confidence_level)

    if pipeline.validator_output:
        v = pipeline.validator_output
        passed = sum(1 for t in v.test_results if t.passed)
        total = len(v.test_results)
        reasoning_steps.append(
            f"[Validator] {passed}/{total} tests passed"
            + (" — REGRESSION DETECTED" if v.regression_detected else "")
        )

    return {
        "run_id": pipeline.run_id,
        "repo": pipeline.repo,
        "issue_number": pipeline.issue_number if not pr_number else None,
        "pr_number": pr_number,
        "classification": classification,
        "root_cause": root_cause,
        "patch_diff": pipeline.final_patch,
        "confidence": round(confidence, 2),
        "reasoning_steps": reasoning_steps,
        "severity": pipeline.strategist_output.severity if pipeline.strategist_output else "Unknown",
        "priority": pipeline.strategist_output.priority if pipeline.strategist_output else "Unknown",
        "affected_files": affected_files,
        "repair_iterations": pipeline.repair_iterations,
        "status": pipeline.status.value,
    }


async def _stream_pipeline(
    repo: str,
    issue_number: int,
    run_id: str,
    pr_number: int | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Run the agent pipeline in a thread and yield SSE events as each phase completes.
    This is the core streaming logic for both issues and PRs.
    """
    loop = asyncio.get_event_loop()
    rag = get_rag_memory()

    # ── Phase events queue ────────────────────────────────────────────────────
    # We run the pipeline synchronously in a thread and emit phase events
    # by monkey-patching the manager's phase methods to put events on a queue.

    queue: asyncio.Queue = asyncio.Queue()

    def run_pipeline():
        """Runs in thread pool. Puts SSE events on the async queue."""
        manager = CentralManager()

        # Wrap each agent's run() to emit SSE events
        original_sentry = manager.sentry.run
        original_strategist = manager.strategist.run
        original_architect = manager.architect.run
        original_developer = manager.developer.run
        original_validator = manager.validator.run

        def sentry_run(*args, **kwargs):
            asyncio.run_coroutine_threadsafe(
                queue.put({"event": "sentry", "data": {"status": "running", "message": "🔍 Sentry scanning repository and issue..."}}),
                loop,
            )
            result = original_sentry(*args, **kwargs)
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "event": "sentry",
                    "data": {
                        "status": "done",
                        "issue_title": result.issue_data.title if result.issue_data else "",
                        "related_issues": result.related_issues,
                        "recent_commits_summary": result.recent_commits_summary[:300],
                        "repo_structure": result.repo_structure[:20],
                    },
                }),
                loop,
            )
            return result

        def strategist_run(*args, **kwargs):
            asyncio.run_coroutine_threadsafe(
                queue.put({"event": "strategist", "data": {"status": "running", "message": "🧠 Strategist classifying issue..."}}),
                loop,
            )
            result = original_strategist(*args, **kwargs)
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "event": "strategist",
                    "data": {
                        "status": "done",
                        "issue_type": result.issue_type,
                        "severity": result.severity,
                        "priority": result.priority,
                        "confidence": result.confidence_level,
                        "summary": result.issue_summary,
                        "suspected_components": result.suspected_components,
                    },
                }),
                loop,
            )
            return result

        def architect_run(*args, **kwargs):
            asyncio.run_coroutine_threadsafe(
                queue.put({"event": "architect", "data": {"status": "running", "message": "📐 Architect planning the fix..."}}),
                loop,
            )
            result = original_architect(*args, **kwargs)
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "event": "architect",
                    "data": {
                        "status": "done",
                        "plan_summary": result.plan_summary,
                        "localized_files": [
                            {"file": loc.file_path, "reason": loc.reason}
                            for loc in result.localized_files[:10]
                        ],
                        "steps": len(result.implementation_steps),
                        "complexity": result.estimated_complexity,
                    },
                }),
                loop,
            )
            return result

        def developer_run(*args, **kwargs):
            asyncio.run_coroutine_threadsafe(
                queue.put({"event": "developer", "data": {"status": "running", "message": "💻 Developer generating patch..."}}),
                loop,
            )
            result = original_developer(*args, **kwargs)
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "event": "developer",
                    "data": {
                        "status": "done",
                        "files_changed": len(result.changes),
                        "explanation": result.explanation[:400],
                        "confidence": result.confidence_level,
                        "patch_preview": result.combined_patch[:500] if result.combined_patch else "",
                    },
                }),
                loop,
            )
            return result

        def validator_run(*args, **kwargs):
            asyncio.run_coroutine_threadsafe(
                queue.put({"event": "validator", "data": {"status": "running", "message": "✅ Validator verifying patch..."}}),
                loop,
            )
            result = original_validator(*args, **kwargs)
            passed = sum(1 for t in result.test_results if t.passed)
            asyncio.run_coroutine_threadsafe(
                queue.put({
                    "event": "validator",
                    "data": {
                        "status": "done",
                        "all_passed": result.all_tests_passed,
                        "tests_passed": passed,
                        "tests_total": len(result.test_results),
                        "regression": result.regression_detected,
                        "feedback": result.feedback_for_developer[:300],
                    },
                }),
                loop,
            )
            return result

        manager.sentry.run = sentry_run
        manager.strategist.run = strategist_run
        manager.architect.run = architect_run
        manager.developer.run = developer_run
        manager.validator.run = validator_run

        try:
            pipeline = manager.run(repo=repo, issue_number=issue_number)
            final = _pipeline_to_response(pipeline, pr_number)

            # Store in RAG memory
            query = f"{repo} #{issue_number}"
            rag.store(query, final)

            asyncio.run_coroutine_threadsafe(
                queue.put({"event": "complete", "data": final}),
                loop,
            )
        except Exception as exc:
            logger.exception("Pipeline error")
            asyncio.run_coroutine_threadsafe(
                queue.put({"event": "error", "data": {"message": str(exc)}}),
                loop,
            )
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None), loop)  # sentinel

    # Start pipeline in thread
    loop.run_in_executor(_executor, run_pipeline)

    # Yield SSE events from queue
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item
        if item.get("event") in ("complete", "error"):
            break


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    """Redirect to documentation."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse()


@app.post("/token", response_model=TokenResponse, tags=["Auth"])
async def get_token(request: TokenRequest):
    """
    Exchange the EXTENSION_API_KEY for a short-lived JWT.
    The Chrome Extension calls this once on install/startup and caches the token.
    """
    if not validate_api_key(request.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    token = create_access_token()
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=JWT_EXPIRE_MINUTES * 60,
    )


@app.post("/analyze-issue", tags=["Analysis"])
async def analyze_issue(
    request: AnalyzeIssueRequest,
    _user: dict = Depends(get_current_user),
):
    """
    Analyze a GitHub Issue using the multi-agent pipeline.
    Returns a Server-Sent Events stream with real-time agent phase updates.

    SSE Event types:
      - sentry      — Reconnaissance phase
      - strategist  — Classification phase
      - architect   — Planning phase
      - developer   — Patch generation phase
      - validator   — Validation phase
      - complete    — Final result (AnalyzeResponse)
      - error       — Pipeline error
    """
    repo = f"{request.repo_owner}/{request.repo_name}"
    run_id = str(uuid.uuid4())[:8]
    logger.info("Analyze issue: %s#%d (run=%s)", repo, request.issue_number, run_id)

    async def event_generator():
        # Initial acknowledgement
        yield {
            "event": "start",
            "data": json.dumps({
                "run_id": run_id,
                "repo": repo,
                "issue_number": request.issue_number,
                "message": f"🚀 Starting SWE-Agent pipeline for {repo}#{request.issue_number}",
            }),
        }

        async for event in _stream_pipeline(repo, request.issue_number, run_id):
            yield {
                "event": event["event"],
                "data": json.dumps(event["data"]),
            }

    return EventSourceResponse(event_generator())


@app.post("/analyze-pr", tags=["Analysis"])
async def analyze_pr(
    request: AnalyzePRRequest,
    _user: dict = Depends(get_current_user),
):
    """
    Analyze a GitHub Pull Request using the multi-agent pipeline.

    The PR is treated as an issue internally — the agent pipeline fetches
    the PR diff, reviews the changed files, and generates a review report
    with potential issues, suggested fixes, and a confidence score.

    Returns SSE stream identical to /analyze-issue.
    """
    repo = f"{request.repo_owner}/{request.repo_name}"
    run_id = str(uuid.uuid4())[:8]
    logger.info("Analyze PR: %s#%d (run=%s)", repo, request.pr_number, run_id)

    # For PRs, we use the PR number as the "issue number" in the pipeline.
    # The GitHub helper in the existing agents can handle PR numbers too
    # since GitHub's API treats PRs as issues.
    async def event_generator():
        yield {
            "event": "start",
            "data": json.dumps({
                "run_id": run_id,
                "repo": repo,
                "pr_number": request.pr_number,
                "message": f"🚀 Starting SWE-Agent PR review for {repo}#{request.pr_number}",
            }),
        }

        async for event in _stream_pipeline(repo, request.pr_number, run_id, pr_number=request.pr_number):
            yield {
                "event": event["event"],
                "data": json.dumps(event["data"]),
            }

    return EventSourceResponse(event_generator())


@app.post("/create-pr", tags=["Actions"])
async def create_pull_request(
    repo_owner: str,
    repo_name: str,
    issue_number: int,
    patch_diff: str,
    branch_name: str | None = None,
    _user: dict = Depends(get_current_user),
):
    """
    Automatically create a GitHub Pull Request from a generated patch.
    Requires GITHUB_TOKEN with write access to the repository.
    """
    if not GITHUB_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GITHUB_TOKEN not configured. Set it in backend/.env",
        )

    try:
        from github import Github, GithubException
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(f"{repo_owner}/{repo_name}")

        # Create branch
        branch = branch_name or f"swe-agent/fix-issue-{issue_number}"
        default_branch = repo.default_branch
        ref = repo.get_git_ref(f"heads/{default_branch}")
        try:
            repo.create_git_ref(f"refs/heads/{branch}", ref.object.sha)
        except GithubException:
            pass  # Branch already exists

        # Create PR
        pr = repo.create_pull(
            title=f"[SWE-Agent] Fix for issue #{issue_number}",
            body=(
                f"## Automated Fix by SWE-Agent\n\n"
                f"This PR was automatically generated by the SWE-Agent Chrome Copilot.\n\n"
                f"**Fixes:** #{issue_number}\n\n"
                f"### Generated Patch\n```diff\n{patch_diff[:3000]}\n```\n"
            ),
            head=branch,
            base=default_branch,
        )
        return {"pr_url": pr.html_url, "pr_number": pr.number, "branch": branch}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── PR-Agent Style Tools ─────────────────────────────────────────────────────

from app.engine.utils.github_helper import post_pr_comment
from app.tools.pr_reviewer import PRReviewerTool, format_review_as_markdown
from app.tools.code_suggestions import CodeSuggestionsTool, format_suggestions_as_markdown
from app.tools.test_generator import TestGeneratorTool, format_tests_as_markdown
from app.tools.pr_agent import PRAgentDispatcher, COMMAND_DESCRIPTIONS
from app.tools.pr_chat import PRChatTool, PRChatRequest, ChatMessage


class ReviewPRRequest(BaseModel):
    """POST /review-pr — review a GitHub PR."""
    repo_owner: str
    repo_name: str
    pr_number: int
    diff_content: str | None = None  # optional pre-fetched diff
    publish_to_github: bool = False


class SuggestFixesRequest(BaseModel):
    """POST /suggest-fixes — generate code suggestions for a PR."""
    repo_owner: str
    repo_name: str
    pr_number: int
    diff_content: str | None = None
    publish_to_github: bool = False


class GenerateTestsRequest(BaseModel):
    """POST /generate-tests — generate tests for PR changes."""
    repo_owner: str
    repo_name: str
    pr_number: int
    diff_content: str | None = None
    publish_to_github: bool = False


class PRAgentRequest(BaseModel):
    """POST /pr-agent — unified command dispatcher."""
    pr_url: str  # Full GitHub PR URL
    command: str  # /review, /improve, /test


from pydantic import BaseModel


@app.post("/review-pr", tags=["PR-Agent Tools"])
async def review_pr(
    request: ReviewPRRequest,
    _user: dict = Depends(get_current_user),
):
    """
    Comprehensive PR review with key issues, scoring, and security analysis.

    Returns a structured review including:
    - Overall quality score (0-100)
    - Effort to review estimate (1-5)
    - Key issues found (with file locations and severity)
    - Security concern analysis
    - Test coverage assessment
    """
    tool = PRReviewerTool()
    repo_full = f"{request.repo_owner}/{request.repo_name}"
    result = await tool.run(
        repo=repo_full,
        pr_number=request.pr_number,
        diff_override=request.diff_content,
    )

    # Done in github page?
    if request.publish_to_github:
        try:
            md = format_review_as_markdown(result)
            post_pr_comment(repo_full, request.pr_number, md)
            logger.info(f"Published review to {repo_full}#{request.pr_number}")
        except Exception as e:
            logger.error(f"Failed to publish review comment: {e}")

    return result.model_dump()


@app.post("/suggest-fixes", tags=["PR-Agent Tools"])
async def suggest_fixes(
    request: SuggestFixesRequest,
    _user: dict = Depends(get_current_user),
):
    """
    Generate inline code improvement suggestions for a PR.

    Returns actionable code suggestions with:
    - Exact existing/improved code snippets
    - Category labels (bug, security, performance, etc.)
    - Importance scores (1-10)
    - One-sentence summaries
    """
    tool = CodeSuggestionsTool()
    repo_full = f"{request.repo_owner}/{request.repo_name}"
    result = await tool.run(
        repo=repo_full,
        pr_number=request.pr_number,
        diff_override=request.diff_content,
    )

    if request.publish_to_github:
        try:
            md = format_suggestions_as_markdown(result)
            post_pr_comment(repo_full, request.pr_number, md)
            logger.info(f"Published suggestions to {repo_full}#{request.pr_number}")
        except Exception as e:
            logger.error(f"Failed to publish suggestions comment: {e}")

    return result.model_dump()


@app.post("/generate-tests", tags=["PR-Agent Tools"])
async def generate_tests(
    request: GenerateTestsRequest,
    _user: dict = Depends(get_current_user),
):
    """
    Auto-generate comprehensive test suites for PR code changes.

    Returns complete, runnable test code with:
    - Setup/teardown fixtures
    - Unit, integration, and edge case tests
    - Test descriptions and priority levels
    """
    tool = TestGeneratorTool()
    repo_full = f"{request.repo_owner}/{request.repo_name}"
    result = await tool.run(
        repo=repo_full,
        pr_number=request.pr_number,
        diff_override=request.diff_content,
    )

    if request.publish_to_github:
        try:
            md = format_tests_as_markdown(result)
            post_pr_comment(repo_full, request.pr_number, md)
            logger.info(f"Published tests to {repo_full}#{request.pr_number}")
        except Exception as e:
            logger.error(f"Failed to publish tests comment: {e}")

    return result.model_dump()


@app.post("/pr-agent", tags=["PR-Agent Tools"])
async def pr_agent_command(
    request: PRAgentRequest,
    _user: dict = Depends(get_current_user),
):
    """
    Unified PR-Agent command dispatcher.

    Send a slash command (/review, /improve, /test) with a GitHub PR URL.
    The dispatcher routes to the appropriate tool and returns structured results.
    """
    dispatcher = PRAgentDispatcher()
    result = await dispatcher.handle_request(
        pr_url=request.pr_url,
        command=request.command,
    )
    return result


@app.get("/pr-agent/commands", tags=["PR-Agent Tools"])
async def list_pr_agent_commands():
    """List available PR-Agent commands and their descriptions."""
    return {
        "commands": COMMAND_DESCRIPTIONS,
        "usage": "POST /pr-agent with {pr_url, command}",
    }


@app.post("/chat-pr", tags=["PR-Agent Tools"])
async def chat_pr(
    request: PRChatRequest,
    _user: dict = Depends(get_current_user),
):
    """
    Chat with your Pull Request code.

    Send a message along with PR context and optional conversation history
    to get AI-powered insights, explanations, reviews, descriptions,
    and code suggestions about your PR.

    Supports multi-turn conversations — include the `history` array
    to maintain context across messages.
    """
    tool = PRChatTool()
    result = await tool.run(
        repo=f"{request.repo_owner}/{request.repo_name}",
        pr_number=request.pr_number,
        message=request.message,
        history=request.history,
        diff_override=request.diff_content,
    )
    return result.model_dump()

@app.post("/upload-doc", tags=["Knowledge Base"])
async def upload_document(
    file: UploadFile = File(...),
    _user: dict = Depends(get_current_user),
):
    """
    Upload a document (PDF, Markdown, or Text) to the RAG knowledge base.
    The agent will use this information to better understand the codebase or domain.
    """
    content = await file.read()
    filename = file.filename
    text = ""

    if filename.endswith(".pdf"):
        from app.algo.pdf_utils import extract_text_from_pdf
        text = extract_text_from_pdf(content)
        if not text:
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")
    else:
        # Assume text/markdown
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Only UTF-8 encoded text or PDF files are supported")

    rag = get_rag_memory()
    rag.store_document(text, {"filename": filename, "uploaded_at": datetime.now().isoformat()})
    
    return {"status": "success", "filename": filename, "message": f"Successfully ingested {filename}"}


@app.get("/list-docs", tags=["Knowledge Base"])
async def list_documents(_user: dict = Depends(get_current_user)):
    """List all documents currently in the RAG knowledge base."""
    rag = get_rag_memory()
    docs = rag.list_documents()
    return {"documents": [
        {"filename": d["metadata"]["filename"], "uploaded_at": d["metadata"]["uploaded_at"]}
        for d in docs
    ]}


@app.post("/ingest-url", tags=["Knowledge Base"])
async def ingest_url(
    payload: dict,
    _user: dict = Depends(get_current_user),
):
    """
    Scrape a URL and store its content in the RAG knowledge base.
    """
    url = payload.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    try:
        import httpx
        import re
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, follow_redirects=True, timeout=10.0)
            resp.raise_for_status()
            
            # Simple HTML to text (not perfect, but good for demo)
            html = resp.text
            # Remove scripts and styles
            html = re.sub(r'<(script|style).*?>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
            # Remove all tags
            text = re.sub(r'<.*?>', ' ', html)
            # Normalize whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            
            if len(text) < 100:
                raise HTTPException(status_code=400, detail="Could not extract meaningful text from URL")

            rag = get_rag_memory()
            rag.store_document(text, {
                "filename": url.split("/")[-1] or "web-page",
                "url": url,
                "uploaded_at": datetime.now().isoformat()
            })
            
            return {"status": "success", "url": url, "message": "Successfully ingested web content"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest URL: {str(e)}")

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info",
    )
