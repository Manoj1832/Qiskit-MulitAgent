"""
Agent-Computer Interface (ACI) Tools.

These tools give agents the ability to interact with the codebase in a
structured way, mirroring the ACI concept from SWE-bench:

  • list_files       – browse directory structure
  • search_string    – grep-like search across files
  • view_file        – read file contents (with line numbers)
  • apply_patch      – apply a unified diff to the codebase
  • run_tests        – execute test commands
  • get_file_context – fetch surrounding lines for a match

In a production deployment these would operate on a local clone inside a
Docker sandbox.  Here we provide both *remote* (GitHub API) and *local*
(filesystem) implementations.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from .github_helper import fetch_file_content, fetch_repo_tree

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# 1. list_files – directory listing
# ──────────────────────────────────────────────────────────────────────────────

def list_files_remote(
    repo: str,
    directory: str = "",
    branch: str = "main",
    max_depth: int = 2,
) -> list[str]:
    """
    List files under *directory* in a GitHub repo.

    Uses the Git tree API, then filters paths that start with *directory*.
    """
    all_paths = fetch_repo_tree(repo, branch=branch, max_depth=max_depth + directory.count("/"))
    if not directory:
        return all_paths

    prefix = directory.rstrip("/") + "/"
    return [p for p in all_paths if p.startswith(prefix)]


def list_files_local(root: str, directory: str = "", max_depth: int = 3) -> list[str]:
    """List files in a local clone."""
    base = Path(root) / directory
    if not base.exists():
        return []

    results: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(base):
        rel = os.path.relpath(dirpath, root)
        depth = rel.count(os.sep)
        if depth > max_depth:
            continue
        for fname in filenames:
            results.append(os.path.join(rel, fname))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# 2. search_string – code search
# ──────────────────────────────────────────────────────────────────────────────

def search_string_local(
    root: str,
    pattern: str,
    file_glob: str = "*.py",
    max_results: int = 30,
) -> list[dict[str, str | int]]:
    """
    Search for *pattern* in all files matching *file_glob* under *root*.

    Returns list of ``{"file": ..., "line": ..., "content": ...}``.
    """
    results: list[dict[str, str | int]] = []
    regex = re.compile(pattern, re.IGNORECASE)

    for fpath in Path(root).rglob(file_glob):
        if len(results) >= max_results:
            break
        try:
            text = fpath.read_text(errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                results.append({
                    "file": str(fpath.relative_to(root)),
                    "line": i,
                    "content": line.strip()[:200],
                })
                if len(results) >= max_results:
                    break

    return results


# ──────────────────────────────────────────────────────────────────────────────
# 3. view_file – read file contents with line numbers
# ──────────────────────────────────────────────────────────────────────────────

def view_file_remote(
    repo: str,
    path: str,
    start_line: int = 1,
    end_line: int = 100,
    ref: str = "main",
) -> str:
    """Fetch a file from GitHub and return lines *start_line*..*end_line*."""
    content = fetch_file_content(repo, path, ref=ref)
    lines = content.splitlines()
    selected = lines[start_line - 1: end_line]
    numbered = [f"{start_line + i:>5} | {ln}" for i, ln in enumerate(selected)]
    return "\n".join(numbered)


def view_file_local(
    root: str,
    path: str,
    start_line: int = 1,
    end_line: int = 100,
) -> str:
    """Read a local file and return lines with numbers."""
    fpath = Path(root) / path
    if not fpath.exists():
        return f"[ERROR] File not found: {path}"
    lines = fpath.read_text(errors="ignore").splitlines()
    selected = lines[start_line - 1: end_line]
    numbered = [f"{start_line + i:>5} | {ln}" for i, ln in enumerate(selected)]
    return "\n".join(numbered)


# ──────────────────────────────────────────────────────────────────────────────
# 4. get_file_context – surrounding lines for a match
# ──────────────────────────────────────────────────────────────────────────────

def get_file_context(
    root: str,
    path: str,
    line: int,
    context: int = 10,
) -> str:
    """Return *context* lines above and below *line* in a local file."""
    start = max(1, line - context)
    end = line + context
    return view_file_local(root, path, start_line=start, end_line=end)


# ──────────────────────────────────────────────────────────────────────────────
# 5. apply_patch – apply a unified diff
# ──────────────────────────────────────────────────────────────────────────────

def apply_patch(root: str, patch: str) -> dict[str, str | bool]:
    """
    Apply a unified diff *patch* to the local clone at *root*.

    Returns ``{"success": True/False, "output": ...}``.
    """
    patch_file = Path(root) / ".swe_agent_patch.diff"
    patch_file.write_text(patch, encoding="utf-8")

    try:
        result = subprocess.run(
            ["git", "apply", "--check", str(patch_file)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "output": f"Patch check failed:\n{result.stderr}",
            }

        # Actually apply
        result = subprocess.run(
            ["git", "apply", str(patch_file)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )

        return {
            "success": result.returncode == 0,
            "output": result.stdout + result.stderr,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Patch application timed out."}
    except FileNotFoundError:
        return {"success": False, "output": "git not found — is git installed?"}
    finally:
        if patch_file.exists():
            patch_file.unlink()


# ──────────────────────────────────────────────────────────────────────────────
# 6. run_tests – execute test commands
# ──────────────────────────────────────────────────────────────────────────────

def run_tests(
    root: str,
    test_path: str = "test/",
    timeout: int = 300,
    extra_args: Optional[list[str]] = None,
) -> dict[str, str | bool | int]:
    """
    Run ``python -m pytest`` on *test_path* inside *root*.

    Returns ``{"success": ..., "returncode": ..., "stdout": ..., "stderr": ...}``.
    """
    cmd = ["python", "-m", "pytest", test_path, "-x", "-v", "--tb=short"]
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-5000:],  # Truncate for LLM context
            "stderr": result.stderr[-2000:],
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Tests timed out after {timeout}s",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "python or pytest not found in PATH",
        }
