from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from yimmparking.interface.build_info import frontend_version, git_head, process_build_info

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


@needs_git
def test_git_head_is_the_full_sha_of_the_checkout(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-q", "-m", "init")
    sha = git_head(tmp_path)
    assert sha is not None and re.fullmatch(r"[0-9a-f]{40}", sha)
    assert process_build_info(tmp_path).version == sha


def test_git_head_is_none_outside_a_checkout(tmp_path: Path) -> None:
    assert git_head(tmp_path / "does-not-exist") is None
    assert git_head(tmp_path) is None  # exists, but not a git work tree


def test_process_start_time_is_timezone_aware_utc(tmp_path: Path) -> None:
    started = datetime.fromisoformat(process_build_info(tmp_path).started_at)
    assert started.tzinfo is not None and started.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_frontend_version_comes_from_the_stamp_file(tmp_path: Path) -> None:
    assert frontend_version(None) is None  # no web build is served
    assert frontend_version(tmp_path) is None  # served, but never stamped
    (tmp_path / "version.txt").write_text("  \n", encoding="utf-8")
    assert frontend_version(tmp_path) is None  # blank is the same as missing
    (tmp_path / "version.txt").write_text("c" * 40 + "\n", encoding="utf-8")
    assert frontend_version(tmp_path) == "c" * 40
