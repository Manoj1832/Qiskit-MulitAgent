"""
PR diff processing utilities — parses GitHub PR diffs into structured hunks.

Inspired by PR-Agent's algo/pr_processing.py which handles:
  - Unified diff parsing into file-level patches
  - Hunk extraction with line numbers
  - Token-aware diff splitting for large PRs
  - Patch formatting with old/new hunk display
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class HunkLine:
    """A single line within a diff hunk."""
    content: str
    line_number_new: Optional[int] = None  # line in the _new_ file
    line_number_old: Optional[int] = None  # line in the _old_ file
    prefix: str = " "  # '+', '-', or ' '


@dataclass
class DiffHunk:
    """A single hunk (@@-block) from a unified diff."""
    header: str  # e.g. "@@ -10,5 +10,7 @@ def func()"
    old_start: int = 0
    old_count: int = 0
    new_start: int = 0
    new_count: int = 0
    lines: list[HunkLine] = field(default_factory=list)
    section_header: str = ""  # e.g. "def func()"

    @property
    def new_lines(self) -> list[HunkLine]:
        """Lines in the new version (unchanged + added)."""
        return [l for l in self.lines if l.prefix in ("+", " ")]

    @property
    def old_lines(self) -> list[HunkLine]:
        """Lines in the old version (unchanged + removed)."""
        return [l for l in self.lines if l.prefix in ("-", " ")]

    @property
    def added_lines(self) -> list[HunkLine]:
        return [l for l in self.lines if l.prefix == "+"]

    @property
    def removed_lines(self) -> list[HunkLine]:
        return [l for l in self.lines if l.prefix == "-"]


@dataclass
class FilePatch:
    """All hunks for a single file in the PR diff."""
    filename: str
    old_filename: Optional[str] = None  # if renamed
    hunks: list[DiffHunk] = field(default_factory=list)
    is_new_file: bool = False
    is_deleted_file: bool = False
    is_binary: bool = False

    @property
    def total_additions(self) -> int:
        return sum(len(h.added_lines) for h in self.hunks)

    @property
    def total_deletions(self) -> int:
        return sum(len(h.removed_lines) for h in self.hunks)

    @property
    def total_changes(self) -> int:
        return self.total_additions + self.total_deletions


# ── Parser ───────────────────────────────────────────────────────────────────

_HUNK_HEADER_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:\s+(.*))?$"
)
_FILE_HEADER_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")
_RENAME_FROM_RE = re.compile(r"^--- a/(.*)$")
_RENAME_TO_RE = re.compile(r"^\+\+\+ b/(.*)$")


def parse_diff(diff_text: str) -> list[FilePatch]:
    """
    Parse a unified diff string into structured FilePatch objects.

    Handles:
      - Standard unified diffs
      - File renames
      - New/deleted files
      - Binary files
    """
    if not diff_text or not diff_text.strip():
        return []

    patches: list[FilePatch] = []
    current_patch: Optional[FilePatch] = None
    current_hunk: Optional[DiffHunk] = None
    new_line_no = 0
    old_line_no = 0

    for raw_line in diff_text.split("\n"):
        # ── New file diff header ─────────────────────────────────────────
        file_match = _FILE_HEADER_RE.match(raw_line)
        if file_match:
            if current_patch:
                patches.append(current_patch)
            current_patch = FilePatch(
                filename=file_match.group(2),
                old_filename=file_match.group(1) if file_match.group(1) != file_match.group(2) else None,
            )
            current_hunk = None
            continue

        if current_patch is None:
            continue

        # ── File mode markers ────────────────────────────────────────────
        if raw_line.startswith("new file mode"):
            current_patch.is_new_file = True
            continue
        if raw_line.startswith("deleted file mode"):
            current_patch.is_deleted_file = True
            continue
        if "Binary files" in raw_line:
            current_patch.is_binary = True
            continue

        # ── Skip --- and +++ headers ─────────────────────────────────────
        if raw_line.startswith("---") or raw_line.startswith("+++"):
            continue
        if raw_line.startswith("index "):
            continue

        # ── Hunk header ──────────────────────────────────────────────────
        hunk_match = _HUNK_HEADER_RE.match(raw_line)
        if hunk_match:
            current_hunk = DiffHunk(
                header=raw_line,
                old_start=int(hunk_match.group(1)),
                old_count=int(hunk_match.group(2) or "1"),
                new_start=int(hunk_match.group(3)),
                new_count=int(hunk_match.group(4) or "1"),
                section_header=hunk_match.group(5) or "",
            )
            current_patch.hunks.append(current_hunk)
            new_line_no = current_hunk.new_start
            old_line_no = current_hunk.old_start
            continue

        # ── Hunk content lines ───────────────────────────────────────────
        if current_hunk is None:
            continue

        if raw_line.startswith("+"):
            current_hunk.lines.append(HunkLine(
                content=raw_line[1:],
                line_number_new=new_line_no,
                prefix="+",
            ))
            new_line_no += 1
        elif raw_line.startswith("-"):
            current_hunk.lines.append(HunkLine(
                content=raw_line[1:],
                line_number_old=old_line_no,
                prefix="-",
            ))
            old_line_no += 1
        elif raw_line.startswith(" ") or raw_line == "":
            content = raw_line[1:] if raw_line.startswith(" ") else ""
            current_hunk.lines.append(HunkLine(
                content=content,
                line_number_new=new_line_no,
                line_number_old=old_line_no,
                prefix=" ",
            ))
            new_line_no += 1
            old_line_no += 1

    # Don't forget the last patch
    if current_patch:
        patches.append(current_patch)

    logger.info(
        "Parsed %d file patches with %d total hunks",
        len(patches),
        sum(len(p.hunks) for p in patches),
    )
    return patches


# ── Formatters ───────────────────────────────────────────────────────────────

def format_diff_for_prompt(
    patches: list[FilePatch],
    max_tokens: int = 8000,
    chars_per_token: float = 3.5,
) -> str:
    """
    Format parsed patches into the PR-Agent style prompt diff format.

    Uses the __new hunk__ / __old hunk__ format with line numbers.
    Truncates if the formatted diff would exceed max_tokens.
    """
    max_chars = int(max_tokens * chars_per_token)
    parts: list[str] = []
    total_chars = 0

    for patch in patches:
        # ── Optimize Token Efficiency: Skip low-value files ──────────────────
        if patch.is_binary:
            file_section = f"\n## File: '{patch.filename}'\n[Binary file - skipped]\n"
            parts.append(file_section)
            total_chars += len(file_section)
            continue

        if _should_skip_file(patch.filename):
            file_section = f"\n## File: '{patch.filename}'\n[Auto-generated/Lock file - skipped to save tokens]\n"
            parts.append(file_section)
            total_chars += len(file_section)
            continue

        file_header = f"\n## File: '{patch.filename}'"
        if patch.is_new_file:
            file_header += " (new file)"
        elif patch.is_deleted_file:
            file_header += " (deleted)"
        elif patch.old_filename:
            file_header += f" (renamed from '{patch.old_filename}')"

        file_parts = [file_header, ""]

        for hunk in patch.hunks:
            # Section header from @@ line
            section = f"@@ ... @@ {hunk.section_header}" if hunk.section_header else "@@ ... @@"
            file_parts.append(section)

            # __new hunk__
            file_parts.append("__new hunk__")
            for line in hunk.lines:
                if line.prefix in ("+", " "):
                    line_no = line.line_number_new or ""
                    prefix = "+" if line.prefix == "+" else " "
                    file_parts.append(f"{line_no:>4} {prefix}{line.content}")

            # __old hunk__ (only if there are removed lines)
            if hunk.removed_lines:
                file_parts.append("__old hunk__")
                for line in hunk.lines:
                    if line.prefix in ("-", " "):
                        prefix = "-" if line.prefix == "-" else " "
                        file_parts.append(f" {prefix}{line.content}")

            file_parts.append("")

        file_section = "\n".join(file_parts)
        total_chars += len(file_section)

        if total_chars > max_chars:
            parts.append(f"\n## File: '{patch.filename}'\n[Content truncated - file too large]\n")
            break
        else:
            parts.append(file_section)

    return "\n".join(parts)


def get_pr_diff_summary(patches: list[FilePatch]) -> dict:
    """Generate a summary of the diff changes."""
    return {
        "total_files": len(patches),
        "total_additions": sum(p.total_additions for p in patches),
        "total_deletions": sum(p.total_deletions for p in patches),
        "total_changes": sum(p.total_changes for p in patches),
        "files": [
            {
                "filename": p.filename,
                "additions": p.total_additions,
                "deletions": p.total_deletions,
                "is_new": p.is_new_file,
                "is_deleted": p.is_deleted_file,
                "is_binary": p.is_binary,
            }
            for p in patches
        ],
    }


def split_diff_for_chunks(
    patches: list[FilePatch],
    max_tokens_per_chunk: int = 4000,
) -> list[list[FilePatch]]:
    """
    Split a large diff into chunks that fit within token limits.
    Used for processing very large PRs in multiple AI calls.
    """
    chunks: list[list[FilePatch]] = []
    current_chunk: list[FilePatch] = []
    current_tokens = 0
    chars_per_token = 3.5

    for patch in patches:
        estimated_chars = sum(
            len(line.content) + 10  # overhead per line
            for hunk in patch.hunks
            for line in hunk.lines
        )
        estimated_tokens = int(estimated_chars / chars_per_token)

        if current_tokens + estimated_tokens > max_tokens_per_chunk and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

        current_chunk.append(patch)
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _should_skip_file(filename: str) -> bool:
    """Check if file should be skipped to save tokens (lockfiles, minified, etc)."""
    skip_patterns = [
        r"package-lock\.json$",
        r"yarn\.lock$",
        r"pnpm-lock\.yaml$",
        r"go\.sum$",
        r"cargo\.lock$",
        r"composer\.lock$",
        r"Gemfile\.lock$",
        r"Pipfile\.lock$",
        r"poetry\.lock$",
        r"\.min\.js$",
        r"\.min\.css$",
        r"\.map$",
        r"\.svg$",
        r"\.png$",
        r"\.jpg$",
        r"\.jpeg$",
        r"\.gif$",
        r"\.ico$",
        r"\.pdf$",
        r"__snapshots__/",
        r"\.ipynb$",  # Notebooks consume massive tokens
    ]
    for pattern in skip_patterns:
        if re.search(pattern, filename, re.IGNORECASE):
            return True
    return False
