"""
Pydantic schemas for the FastAPI layer.
These are the HTTP-level contracts (separate from domain/models.py which are
the inter-agent contracts).
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Request Models ────────────────────────────────────────────────────────────

class AnalyzeIssueRequest(BaseModel):
    """POST /analyze-issue — analyze a GitHub issue."""
    repo_owner: str = Field(..., description="GitHub repository owner")
    repo_name: str = Field(..., description="GitHub repository name")
    issue_number: int = Field(..., description="GitHub issue number")
    # Optional pre-extracted data from the extension DOM scrape
    issue_title: Optional[str] = None
    issue_body: Optional[str] = None
    comments: list[str] = Field(default_factory=list)


class AnalyzePRRequest(BaseModel):
    """POST /analyze-pr — analyze a GitHub Pull Request."""
    repo_owner: str = Field(..., description="GitHub repository owner")
    repo_name: str = Field(..., description="GitHub repository name")
    pr_number: int = Field(..., description="GitHub PR number")
    # Optional pre-extracted data from the extension DOM scrape
    pr_title: Optional[str] = None
    pr_body: Optional[str] = None
    diff_content: Optional[str] = None
    changed_files: list[str] = Field(default_factory=list)
    review_comments: list[str] = Field(default_factory=list)


class TokenRequest(BaseModel):
    """POST /token — exchange API key for JWT."""
    api_key: str


# ── SSE Event Models ──────────────────────────────────────────────────────────

class SSEEvent(BaseModel):
    """A single Server-Sent Event payload."""
    event: str  # phase name: sentry | strategist | architect | developer | validator | complete | error
    data: dict[str, Any]
    run_id: Optional[str] = None


# ── Response Models ───────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    agents: list[str] = ["sentry", "strategist", "architect", "developer", "validator"]


class AnalyzeResponse(BaseModel):
    """Final structured response (also sent as the 'complete' SSE event)."""
    run_id: str
    repo: str
    issue_number: Optional[int] = None
    pr_number: Optional[int] = None
    classification: str  # bug / enhancement / user-error
    root_cause: str
    patch_diff: str
    confidence: float  # 0.0 - 1.0
    reasoning_steps: list[str]
    severity: str
    priority: str
    affected_files: list[str]
    repair_iterations: int
    status: str  # completed | failed
