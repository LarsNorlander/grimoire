"""Diff logic for grimoire.

Compares three edges of the rite/tome/manifest state graph:
  - drift:  tome vs. manifest hashes       (what's changed on disk since last cast)
  - cast:   tome vs. fresh rebuild         (what `grimoire cast` would change)
  - accept: tome vs. rite source           (what `--accept` would pull back)
"""

import difflib
import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from arcana.tome import CopyOp, RiteContext, WriteOp


class Kind(str, Enum):
    COPY = "copy"
    WRITE = "write"


class Direction(str, Enum):
    """The three comparison axes a DiffResult carries."""
    DRIFT = "drift"
    CAST = "cast"
    ACCEPT = "accept"


class Status(str, Enum):
    CLEAN = "."
    MODIFIED = "M"
    ADDED = "A"          # tome has file that the comparison side doesn't
    DELETED = "D"        # comparison side has file that tome doesn't
    UNEVALUATED = "?"    # write() rite, --build not passed
    NA = "-"             # comparison doesn't apply


# Statuses that represent a real change (for exit codes + conflict detection).
CHANGED = {Status.MODIFIED, Status.ADDED, Status.DELETED}


@dataclass
class FilePlan:
    """One file a rite manages, with everything needed to diff it."""
    tool: str
    filename: str
    kind: Kind
    rite_source: Path | None       # None for write()
    tome_path: Path
    planned_content: bytes | None  # None if write() and --build not set

    @property
    def manifest_key(self) -> str:
        return f"{self.tool}/{self.filename}"


@dataclass
class DiffResult:
    plan: FilePlan
    statuses: dict[Direction, Status]
    tome_content: bytes | None
    manifest_hash: str | None

    def status(self, d: Direction) -> Status:
        return self.statuses[d]

    def is_clean_in(self, selected: set[Direction]) -> bool:
        return all(self.statuses[d] not in CHANGED for d in selected)

    @property
    def has_conflict(self) -> bool:
        # Conflict requires both sides to be actually evaluated changes.
        return (
            self.statuses[Direction.DRIFT] in CHANGED
            and self.statuses[Direction.CAST] in CHANGED
        )


# --- Plan extraction (no disk side effects) ---

def plan_rite(ctx: RiteContext, build: bool) -> list[FilePlan]:
    """Extract FilePlans from a RiteContext that has registered ops but not executed them."""
    plans: list[FilePlan] = []
    for op in ctx._ops:
        if isinstance(op, CopyOp):
            for f in op.files:
                src = ctx.rite_dir / f
                plans.append(FilePlan(
                    tool=ctx.tool,
                    filename=f,
                    kind=Kind.COPY,
                    rite_source=src,
                    tome_path=ctx.tome_dir / f,
                    planned_content=src.read_bytes() if src.exists() else None,
                ))
        elif isinstance(op, WriteOp):
            content_bytes: bytes | None = None
            if build:
                raw = op.content
                if callable(raw):
                    raw = raw(
                        profile=ctx.profile,
                        rite_dir=ctx.rite_dir,
                        grimoire_root=ctx.grimoire_root,
                    )
                content_bytes = raw.encode() if isinstance(raw, str) else raw
            plans.append(FilePlan(
                tool=ctx.tool,
                filename=op.filename,
                kind=Kind.WRITE,
                rite_source=None,
                tome_path=ctx.tome_dir / op.filename,
                planned_content=content_bytes,
            ))
        # LinkOp and HookOp have no file-level diff semantics.
    return plans


# --- Diff computation ---

def compute_diff(plan: FilePlan, manifest: dict[str, str], build: bool) -> DiffResult:
    tome_content = plan.tome_path.read_bytes() if plan.tome_path.exists() else None
    manifest_hash = manifest.get(plan.manifest_key)

    # A: drift (tome vs. manifest)
    if tome_content is None:
        drift = Status.DELETED if manifest_hash is not None else Status.CLEAN
    elif manifest_hash is None:
        drift = Status.ADDED
    else:
        current_hash = hashlib.sha256(tome_content).hexdigest()
        drift = Status.CLEAN if current_hash == manifest_hash else Status.MODIFIED

    # B: cast (tome vs. fresh rebuild)
    if plan.kind == Kind.WRITE and not build:
        cast = Status.UNEVALUATED
    elif plan.planned_content is None and tome_content is None:
        cast = Status.CLEAN
    elif plan.planned_content is None:
        cast = Status.DELETED
    elif tome_content is None:
        cast = Status.ADDED
    else:
        cast = Status.CLEAN if plan.planned_content == tome_content else Status.MODIFIED

    # C: accept (tome vs. rite source).
    # `--accept` is tome→rite-source, gated on `_is_externally_modified` which
    # requires the tome file to exist — so a missing tome is a no-op, not a change.
    if plan.kind == Kind.WRITE:
        accept = Status.NA
    elif tome_content is None:
        accept = Status.CLEAN
    elif plan.rite_source is None or not plan.rite_source.exists():
        accept = Status.DELETED
    else:
        source = plan.rite_source.read_bytes()
        accept = Status.CLEAN if source == tome_content else Status.MODIFIED

    return DiffResult(
        plan=plan,
        statuses={
            Direction.DRIFT: drift,
            Direction.CAST: cast,
            Direction.ACCEPT: accept,
        },
        tome_content=tome_content,
        manifest_hash=manifest_hash,
    )


# --- Formatting ---

_REASONS = {
    (Direction.DRIFT, Status.CLEAN): "clean",
    (Direction.DRIFT, Status.MODIFIED): "tome modified since last cast",
    (Direction.DRIFT, Status.ADDED): "tome present but no manifest entry",
    (Direction.DRIFT, Status.DELETED): "tome missing — was last-built",
    (Direction.CAST, Status.CLEAN): "clean",
    (Direction.CAST, Status.MODIFIED): "rite source / generator output differs from tome",
    (Direction.CAST, Status.ADDED): "would be created on next cast",
    (Direction.CAST, Status.DELETED): "rite source missing — cast would fail or no-op",
    (Direction.CAST, Status.UNEVALUATED): "write() — pass --build to evaluate",
    (Direction.ACCEPT, Status.CLEAN): "clean",
    (Direction.ACCEPT, Status.MODIFIED): "tome differs from rite source",
    (Direction.ACCEPT, Status.DELETED): "no matching rite source",
    (Direction.ACCEPT, Status.NA): "write() rites aren't round-trippable",
}


def format_summary(results: list[DiffResult], selected: set[Direction]) -> str:
    shown = [r for r in results if not r.is_clean_in(selected)]
    lines: list[str] = []
    conflicts_meaningful = {Direction.DRIFT, Direction.CAST}.issubset(selected)
    conflicts = 0

    for r in shown:
        if r.has_conflict and conflicts_meaningful:
            conflicts += 1
        lines.append(f"{r.plan.tool}/{r.plan.filename}  [{r.plan.kind.value}()]")
        for direction in Direction:
            if direction not in selected:
                continue
            status = r.status(direction)
            reason = _REASONS.get((direction, status), "")
            lines.append(f"  {direction.value:<8} {status.value}   {reason}")
        if r.has_conflict and conflicts_meaningful:
            lines.append("  ⚠ potential conflict: live edits + pending cast changes")
        lines.append("")

    # Footer
    change_count = sum(
        1 for r in results for d in selected if r.status(d) in CHANGED
    )
    conf_suffix = (
        f" ({conflicts} potential conflict{'s' if conflicts != 1 else ''})"
        if conflicts
        else ""
    )
    file_word = "file" if len(shown) == 1 else "files"
    change_word = "change" if change_count == 1 else "changes"
    lines.append(f"{len(shown)} {file_word} shown, {change_count} {change_word}{conf_suffix}")
    return "\n".join(lines)


def format_full(results: list[DiffResult], selected: set[Direction]) -> str:
    parts: list[str] = []
    for r in results:
        if r.is_clean_in(selected):
            continue
        parts.append(f"=== {r.plan.tool}/{r.plan.filename}  [{r.plan.kind.value}()] ===")

        drift = r.status(Direction.DRIFT)
        if Direction.DRIFT in selected and drift != Status.CLEAN:
            parts.append(f"\n--- drift: {_REASONS[(Direction.DRIFT, drift)]}")
            if r.manifest_hash:
                parts.append(f"  last-built hash: {r.manifest_hash[:16]}…")
            if r.tome_content is not None:
                h = hashlib.sha256(r.tome_content).hexdigest()
                parts.append(f"  current hash:    {h[:16]}…")
            parts.append("  (content diff not available — manifest stores hashes only)")

        cast = r.status(Direction.CAST)
        if Direction.CAST in selected and cast in CHANGED:
            parts.append(f"\n--- cast: {_REASONS[(Direction.CAST, cast)]}")
            parts.append(_unified_diff(
                r.tome_content,
                r.plan.planned_content,
                f"tome/{r.plan.tool}/{r.plan.filename}",
                f"rebuilt {r.plan.tool}/{r.plan.filename}",
            ))
        elif Direction.CAST in selected and cast == Status.UNEVALUATED:
            parts.append(f"\n--- cast: {_REASONS[(Direction.CAST, cast)]}")

        accept = r.status(Direction.ACCEPT)
        if Direction.ACCEPT in selected and accept in CHANGED:
            parts.append(f"\n--- accept: {_REASONS[(Direction.ACCEPT, accept)]}")
            source_bytes = (
                r.plan.rite_source.read_bytes()
                if r.plan.rite_source and r.plan.rite_source.exists()
                else None
            )
            parts.append(_unified_diff(
                source_bytes,
                r.tome_content,
                f"rites/{r.plan.tool}/{r.plan.filename}",
                f"tome/{r.plan.tool}/{r.plan.filename}",
            ))

        parts.append("")
    return "\n".join(parts)


def _unified_diff(a: bytes | None, b: bytes | None, a_name: str, b_name: str) -> str:
    a_lines = (a or b"").decode(errors="replace").splitlines(keepends=True)
    b_lines = (b or b"").decode(errors="replace").splitlines(keepends=True)
    diff = "".join(difflib.unified_diff(a_lines, b_lines, fromfile=a_name, tofile=b_name))
    return diff if diff else "  (no textual diff — files are identical or both empty)"
