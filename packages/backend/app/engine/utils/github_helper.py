"""
GitHub REST API helper — fetches issues, PRs, repo metadata, and file trees.

Used by the **Sentry** agent to gather raw data about the repository
and the issue under investigation.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from .config import get_github_token

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


# ── Low-level ─────────────────────────────────────────────────────────────────

def _headers() -> dict[str, str]:
    """Build request headers, optionally including auth."""
    h: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = get_github_token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(url: str, params: Optional[dict[str, Any]] = None) -> Any:
    """GET a GitHub API URL and return parsed JSON."""
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _post(url: str, data: dict[str, Any]) -> Any:
    """POST to a GitHub API URL and return parsed JSON."""
    resp = requests.post(url, headers=_headers(), json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── Comments ─────────────────────────────────────────────────────────────────

def post_pr_comment(repo: str, pr_number: int, body: str) -> dict[str, Any]:
    """Post a comment on a Pull Request."""
    logger.info("Posting comment on %s#%d", repo, pr_number)
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    return _post(url, {"body": body})


def post_issue_comment(repo: str, issue_number: int, body: str) -> dict[str, Any]:
    """Post a comment on an Issue."""
    logger.info("Posting comment on %s#%d", repo, issue_number)
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments"
    return _post(url, {"body": body})


# ── Issue ─────────────────────────────────────────────────────────────────────

def fetch_issue(repo: str, issue_number: int) -> dict[str, Any]:
    """
    Fetch full issue data including comments.

    Returns a dict with keys:
        title, body, labels, state, author, created_at,
        comments, linked_pr_numbers, linked_pr_files, milestone.
    """
    logger.info("Fetching issue #%d from %s …", issue_number, repo)

    issue_data = _get(f"{GITHUB_API}/repos/{repo}/issues/{issue_number}")

    # Comments
    comments_url = issue_data.get("comments_url", "")
    raw_comments: list[dict] = _get(comments_url) if comments_url else []
    comments = [c["body"] for c in raw_comments if c.get("body")]

    # Labels
    labels = [lbl["name"] for lbl in issue_data.get("labels", [])]

    # Linked PR files (best-effort)
    linked_pr_numbers: list[int] = []
    linked_pr_files: list[str] = []
    pr_info = issue_data.get("pull_request")
    if pr_info:
        pr_url = pr_info.get("url", "")
        linked_pr_numbers.append(issue_number)
        if pr_url:
            try:
                pr_files = _get(f"{pr_url}/files")
                linked_pr_files = [f["filename"] for f in pr_files]
            except Exception:
                logger.warning("Could not fetch PR files for #%d", issue_number)

    # Milestone
    milestone = None
    if issue_data.get("milestone"):
        milestone = issue_data["milestone"].get("title")

    return {
        "repo": repo,
        "issue_number": issue_number,
        "title": issue_data.get("title", ""),
        "body": issue_data.get("body", "") or "",
        "labels": labels,
        "state": issue_data.get("state", "open"),
        "author": (issue_data.get("user") or {}).get("login", ""),
        "created_at": issue_data.get("created_at"),
        "comments": comments,
        "linked_pr_numbers": linked_pr_numbers,
        "linked_pr_files": linked_pr_files,
        "milestone": milestone,
    }


# ── Repository Metadata ──────────────────────────────────────────────────────

def fetch_repo_info(repo: str) -> dict[str, Any]:
    """Fetch basic repository metadata (language, description, etc.)."""
    return _get(f"{GITHUB_API}/repos/{repo}")


def fetch_repo_tree(
    repo: str,
    branch: str = "main",
    max_depth: int = 3,
) -> list[str]:
    """
    Fetch the file tree of a repo (up to *max_depth* levels).

    Returns a list of paths like ``["qiskit/circuit/gate.py", ...]``.
    """
    try:
        data = _get(
            f"{GITHUB_API}/repos/{repo}/git/trees/{branch}",
            params={"recursive": "1"},
        )
    except requests.HTTPError:
        # Fallback to 'master' branch
        try:
            data = _get(
                f"{GITHUB_API}/repos/{repo}/git/trees/master",
                params={"recursive": "1"},
            )
        except requests.HTTPError:
            logger.warning("Could not fetch repo tree for %s", repo)
            return []

    paths: list[str] = []
    for item in data.get("tree", []):
        path = item.get("path", "")
        depth = path.count("/")
        if depth <= max_depth:
            paths.append(path)
    return paths


def fetch_file_content(repo: str, path: str, ref: str = "main") -> str:
    """Fetch the raw content of a single file from the repo."""
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def search_code_in_repo(
    repo: str,
    query: str,
    language: Optional[str] = None,
    max_results: int = 10,
) -> list[dict[str, str]]:
    """
    Use GitHub code-search API to find files matching *query* in *repo*.

    Returns list of dicts with keys: name, path, url.
    """
    q = f"{query} repo:{repo}"
    if language:
        q += f" language:{language}"

    try:
        data = _get(
            f"{GITHUB_API}/search/code",
            params={"q": q, "per_page": max_results},
        )
    except requests.HTTPError as exc:
        logger.warning("Code search failed: %s", exc)
        return []

    results: list[dict[str, str]] = []
    for item in data.get("items", []):
        results.append({
            "name": item.get("name", ""),
            "path": item.get("path", ""),
            "url": item.get("html_url", ""),
        })
    return results


def fetch_recent_commits(
    repo: str,
    path: Optional[str] = None,
    max_count: int = 10,
) -> list[dict[str, str]]:
    """Fetch recent commits, optionally filtered to a specific path."""
    params: dict[str, Any] = {"per_page": max_count}
    if path:
        params["path"] = path
    data = _get(f"{GITHUB_API}/repos/{repo}/commits", params=params)

    commits: list[dict[str, str]] = []
    for c in data:
        commits.append({
            "sha": c.get("sha", "")[:8],
            "message": (c.get("commit", {}).get("message", "")).split("\n")[0],
            "author": (c.get("commit", {}).get("author", {}).get("name", "")),
            "date": (c.get("commit", {}).get("author", {}).get("date", "")),
        })
    return commits


def search_related_issues(
    repo: str,
    keywords: list[str],
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Search for related open issues using keyword query."""
    q = " ".join(keywords[:5]) + f" repo:{repo} is:issue"
    try:
        data = _get(
            f"{GITHUB_API}/search/issues",
            params={"q": q, "per_page": max_results, "sort": "relevance"},
        )
    except requests.HTTPError:
        return []

    results: list[dict[str, Any]] = []
    for item in data.get("items", []):
        results.append({
            "number": item.get("number"),
            "title": item.get("title", ""),
            "state": item.get("state", ""),
            "url": item.get("html_url", ""),
        })
    return results
