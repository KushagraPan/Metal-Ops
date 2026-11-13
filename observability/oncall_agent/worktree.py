"""Isolated Git worktree management for the On-Call Agent."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

logger = logging.getLogger("metalops.oncall_worktree")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class WorktreeError(Exception):
    """Raised when git worktree operations fail."""


class WorktreeInfo:
    """Represents an active isolated Git worktree."""

    def __init__(self, path: Path, branch: str) -> None:
        self.path = Path(path)
        self.branch = branch

    def __iter__(self):
        """Allow tuple unpacking: wt_path, branch = mgr.create_worktree(...)"""
        return iter((self.path, self.branch))

    def __fspath__(self) -> str:
        return str(self.path)

    def __str__(self) -> str:
        return str(self.path)

    def exists(self) -> bool:
        return self.path.exists()

    def __truediv__(self, other: str | Path) -> Path:
        return self.path / other


class WorktreeManager:
    """Manages isolated git worktrees for incident reproduction, testing, and fixes."""

    def __init__(
        self,
        repo_root: str | Path | None = None,
        worktree_base: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root or os.getcwd()).resolve()
        self.worktree_base = (
            Path(worktree_base).resolve()
            if worktree_base
            else self.repo_root.parent / "metalops-oncall-worktrees"
        )

    def _ensure_unique_branch_name(self, base_branch: str) -> str:
        """Return a branch name that does not collide with existing refs."""
        candidate = base_branch
        suffix = 1
        while True:
            res = subprocess.run(
                ["git", "rev-parse", "--verify", f"refs/heads/{candidate}"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                # Branch does not exist
                return candidate
            candidate = f"{base_branch}-{suffix}"
            suffix += 1

    def _ensure_unique_target_dir(self, clean_tag: str) -> Path:
        """Return a target directory that does not collide with existing preserved worktrees."""
        target_dir = self.worktree_base / f"wt-{clean_tag}"
        if not target_dir.exists():
            return target_dir

        suffix = 1
        while True:
            candidate = self.worktree_base / f"wt-{clean_tag}-{suffix}"
            if not candidate.exists():
                return candidate
            suffix += 1

    def create_worktree(self, branch_name: str, start_point: str = "HEAD") -> WorktreeInfo:
        """Create a dedicated, isolated git worktree for a fix branch.

        Returns:
            WorktreeInfo object yielding (worktree_directory_path, unique_branch_name).
        """
        self.prune_worktrees()
        unique_branch = self._ensure_unique_branch_name(branch_name)
        clean_tag = unique_branch.replace("/", "-").replace("\\", "-").strip("-")
        target_dir = self._ensure_unique_target_dir(clean_tag)

        self.worktree_base.mkdir(parents=True, exist_ok=True)

        cmd = ["git", "worktree", "add", "-b", unique_branch, str(target_dir), start_point]
        try:
            res = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                err_msg = res.stderr.strip() or res.stdout.strip() or "Unknown git worktree error"
                raise WorktreeError(f"Failed to create git worktree at {target_dir}: {err_msg}")
        except WorktreeError:
            raise
        except Exception as exc:
            raise WorktreeError(f"Could not execute git worktree add: {exc}") from exc

        logger.info("Created isolated git worktree at %s (branch: %s)", target_dir, unique_branch)
        return WorktreeInfo(target_dir, unique_branch)

    def prune_worktrees(self) -> None:
        """Prune stale git worktree administrative metadata."""
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            logger.warning("git worktree prune failed: %s", exc)

    def remove_worktree(
        self,
        worktree_path: str | Path | WorktreeInfo,
        force: bool = True,
        preserve: bool = False,
    ) -> bool:
        """Remove a git worktree. If preserve=True, leaves the worktree intact for inspection."""
        if isinstance(worktree_path, WorktreeInfo):
            path = worktree_path.path.resolve()
        else:
            path = Path(worktree_path).resolve()
        if preserve:
            logger.info("Preserving worktree at %s for human review / inspection", path)
            return False

        if not path.exists():
            self.prune_worktrees()
            return True

        cmd = ["git", "worktree", "remove", str(path)]
        if force:
            cmd.insert(3, "--force")

        try:
            res = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                logger.warning("git worktree remove failed: %s; falling back to shutil.rmtree", res.stderr.strip())
                shutil.rmtree(path, ignore_errors=True)
            self.prune_worktrees()
            logger.info("Removed worktree at %s", path)
            return True
        except Exception as exc:
            logger.error("Error removing worktree %s: %s", path, exc)
            return False

    @contextmanager
    def managed_worktree(
        self,
        branch_name: str,
        preserve: bool = True,
    ) -> Generator[tuple[Path, str], None, None]:
        """Context manager yielding (worktree_path, branch_name), preserving evidence if preserve=True."""
        wt_path, unique_branch = self.create_worktree(branch_name)
        try:
            yield wt_path, unique_branch
        finally:
            self.remove_worktree(wt_path, force=True, preserve=preserve)
