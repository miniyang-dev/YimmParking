"""Which build is answering: the backend's git commit, when this process started, and the commit the
served web build was made from.

A deploy check uses it to prove the new version is the one actually running — not an old process
that never restarted, and not a stale web build behind the new API.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_SHA = re.compile(r"[0-9a-f]{40}")
VERSION_FILE = "version.txt"  # written next to index.html by deploy/deploy.sh after `pnpm build`


@dataclass(frozen=True, slots=True)
class BuildInfo:
    version: str | None  # git HEAD of the checkout when this process started; None if unknown
    started_at: str  # ISO-8601 UTC


def git_head(repo_root: Path) -> str | None:
    """The full commit sha of the checkout, or None when this is not a git checkout (or no git)."""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = done.stdout.strip()
    return sha if _SHA.fullmatch(sha) else None


def process_build_info(repo_root: Path) -> BuildInfo:
    """Read once, when the app is created: the version a process reports must be the code it loaded,
    not whatever the checkout was moved to afterwards."""
    return BuildInfo(
        version=git_head(repo_root),
        started_at=datetime.now(UTC).isoformat(timespec="milliseconds"),
    )


def frontend_version(web_dist: Path | None) -> str | None:
    """The commit the served web build was made from. Read on every call so a rebuild shows up
    without restarting the API (the static files are served straight from disk)."""
    if web_dist is None:
        return None
    try:
        text = (web_dist / VERSION_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None
