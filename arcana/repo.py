"""Updating the grimoire checkout itself: a fast-forward pull, or a report.

Every function here returns data; the CLI turns it into output. Nothing
merges, rebases, stashes, or resets: when a fast-forward isn't possible, the
result says why and the user resolves it with git, where the history is.
"""

import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Outcome(StrEnum):
    UP_TO_DATE = "up-to-date"
    AHEAD = "ahead"  # nothing incoming; local commits not yet pushed
    FAST_FORWARDED = "fast-forwarded"
    DIRTY = "dirty"
    DIVERGED = "diverged"  # both ahead and behind: a fast-forward is impossible
    NO_UPSTREAM = "no-upstream"
    FETCH_FAILED = "fetch-failed"
    MERGE_FAILED = "merge-failed"


@dataclass
class Update:
    outcome: Outcome
    old_head: str = ""
    new_head: str = ""
    incoming: list[str] = field(default_factory=list)  # one-line log, oldest first
    local_only: list[str] = field(default_factory=list)  # commits upstream lacks
    changed_paths: list[str] = field(default_factory=list)
    dirty_files: list[str] = field(default_factory=list)
    error: str = ""

    def suggests(self) -> list[str]:
        """Verbs worth running after a fast-forward, from what changed."""
        verbs: list[str] = []
        if any(p.startswith("runes/") for p in self.changed_paths):
            verbs.append("inscribe")
        if any(p.startswith(("rites/", "arcana/")) for p in self.changed_paths):
            verbs.append("cast")
        return verbs


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )


def _lines(result: subprocess.CompletedProcess) -> list[str]:
    return [line for line in result.stdout.splitlines() if line.strip()]


def update(root: Path) -> Update:
    """Fast-forward the checkout at `root` to its upstream, if that is safe."""
    dirty = _lines(_git(root, "status", "--porcelain"))
    if dirty:
        return Update(Outcome.DIRTY, dirty_files=dirty)

    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream.returncode != 0:
        return Update(Outcome.NO_UPSTREAM, error=upstream.stderr.strip())
    upstream_ref = upstream.stdout.strip()

    fetched = _git(root, "fetch", "--quiet")
    if fetched.returncode != 0:
        return Update(Outcome.FETCH_FAILED, error=fetched.stderr.strip())

    old_head = _git(root, "rev-parse", "HEAD").stdout.strip()
    counts = _git(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream_ref}")
    ahead, behind = (int(n) for n in counts.stdout.split())

    local_only = _lines(_git(root, "log", "--oneline", f"{upstream_ref}..HEAD"))
    if ahead and behind:
        return Update(Outcome.DIVERGED, old_head=old_head, local_only=local_only)
    if ahead:
        return Update(
            Outcome.AHEAD, old_head=old_head, new_head=old_head, local_only=local_only
        )
    if not behind:
        return Update(Outcome.UP_TO_DATE, old_head=old_head, new_head=old_head)

    incoming = _lines(
        _git(root, "log", "--oneline", "--reverse", f"HEAD..{upstream_ref}")
    )
    changed = _lines(_git(root, "diff", "--name-only", f"HEAD..{upstream_ref}"))
    merged = _git(root, "merge", "--ff-only", upstream_ref)
    if merged.returncode != 0:
        return Update(
            Outcome.MERGE_FAILED, old_head=old_head, error=merged.stderr.strip()
        )
    new_head = _git(root, "rev-parse", "HEAD").stdout.strip()
    return Update(
        Outcome.FAST_FORWARDED,
        old_head=old_head,
        new_head=new_head,
        incoming=incoming,
        changed_paths=changed,
    )
