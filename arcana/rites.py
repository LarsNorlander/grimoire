"""Discovering, loading, and running rites against a grimoire root.

The CLI parses arguments and prints; this module does the work, with the
root passed in explicitly so nothing here knows where the checkout lives.
Progress lines go to stdout the same way `RiteContext` reports its ops, so a
cast reads as one stream.
"""

import importlib.util
import os
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

from arcana.tome import (
    RiteContext,
    RiteSkipped,
    load_manifest,
    parse_rite_profiles,
    save_manifest,
)

VALID_PROFILES = ("work", "personal")


class RiteNotFound(Exception):
    def __init__(self, tool: str):
        super().__init__(f"no rite found for '{tool}'")
        self.tool = tool


def rite_path(root: Path, tool: str) -> Path:
    return root / "rites" / tool / "rite"


def discover(root: Path, tools: tuple[str, ...] = ()) -> list[Path]:
    """Rite scripts to operate on.

    Named tools must exist (``RiteNotFound`` otherwise). With no names, every
    executable ``rites/*/rite`` in sorted order — a non-executable rite is
    treated as parked, not broken.
    """
    if tools:
        paths = []
        for tool in tools:
            path = rite_path(root, tool)
            if not path.is_file():
                raise RiteNotFound(tool)
            paths.append(path)
        return paths
    return sorted(p for p in root.glob("rites/*/rite") if os.access(p, os.X_OK))


def allowed_under(path: Path, profile: str) -> bool:
    """Whether a rite's `# profile:` directive admits this profile."""
    allowed = parse_rite_profiles(path)
    return allowed is None or profile in allowed


def load_rite(path: Path, profile: str, root: Path, *,
              force: bool = False, accepting: bool = False) -> RiteContext:
    """Execute a rite module so its ops register on a new RiteContext.

    Honors `# profile: <names>` frontmatter — if the rite declares profile
    compatibility and we're not in accept mode, raises ``RiteSkipped`` before
    the module is imported. Accept mode bypasses the gate (you might want to
    salvage files from a work-profile rite while on personal).
    """
    tool = path.parent.name
    if not accepting:
        allowed = parse_rite_profiles(path)
        if allowed:
            unknown = allowed - set(VALID_PROFILES)
            if unknown:
                print(
                    f"  WARNING {tool}: unknown profile(s) in frontmatter: "
                    f"{', '.join(sorted(unknown))} "
                    f"(expected one of: {', '.join(VALID_PROFILES)})",
                    file=sys.stderr,
                )
            if profile not in allowed:
                raise RiteSkipped(
                    f"  skipped {tool} — requires {'/'.join(sorted(allowed))} profile"
                )
    ctx = RiteContext(profile, root, tool, force=force, accepting=accepting)
    RiteContext._current = ctx
    try:
        spec = importlib.util.spec_from_file_location(
            "rite", path, loader=SourceFileLoader("rite", str(path))
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        RiteContext._current = None
    return ctx


def run_rite(path: Path, profile: str, root: Path, *,
             force: bool, accepting: bool, dry_run: bool = False) -> None:
    try:
        ctx = load_rite(path, profile, root, force=force, accepting=accepting)
    except RiteSkipped as e:
        print(e)
        return
    ctx.execute(dry_run=dry_run)


def build_rites(root: Path, profile: str, *, force: bool, dry_run: bool = False,
                tools: tuple[str, ...] = ()) -> list[tuple[str, Exception]]:
    """Cast the given rites (all, when none are named).

    Returns the failures as (tool, error) pairs rather than exiting, so the
    caller decides how to report them. After a clean, full, non-dry run the
    manifest is garbage-collected.
    """
    paths = discover(root, tools)

    print("Building rites...")
    errors: list[tuple[str, Exception]] = []
    # Track keys owned by rites that ran this pass, so we can GC stale
    # manifest entries from tools that have stopped managing a file.
    touched: set[str] = set()
    built_tools: set[str] = set()
    for path in paths:
        try:
            ctx = load_rite(path, profile, root, force=force)
        except RiteSkipped as e:
            print(e)
            continue
        except Exception as e:
            errors.append((path.parent.name, e))
            continue
        built_tools.add(ctx.tool)
        touched.update(ctx.registered_keys())
        try:
            ctx.execute(dry_run=dry_run)
        except Exception as e:
            errors.append((path.parent.name, e))
    print()

    # Skipped rites (e.g. profile-gated) are preserved — their entries are
    # valid under the matching profile.
    if not errors and not tools and not dry_run:
        gc_manifest(root, touched, built_tools)
    return errors


def gc_manifest(root: Path, touched: set[str], built_tools: set[str]) -> None:
    """Prune stale manifest entries and the tome files they pointed at.

    A file is stale when either (a) the rite no longer exists at all, or
    (b) the rite built this pass but didn't register the file. Profile-
    skipped rites are preserved — their entries remain valid under the
    matching profile.

    Symlinks in the user's home directory pointing at pruned tome files
    are *not* cleaned automatically — grimoire doesn't track link targets
    in the manifest, so it doesn't know where the rite put them. We print
    a notice when pruning entries for tools that no longer have a rite.
    """
    tome_root = root / "tome"
    manifest = load_manifest(tome_root)
    if not manifest:
        return
    extant_tools = {p.parent.name for p in discover(root)}
    stale: set[str] = set()
    for key in manifest:
        tool = key.split("/", 1)[0]
        if tool not in extant_tools:
            stale.add(key)  # tool removed entirely
        elif tool in built_tools and key not in touched:
            stale.add(key)  # tool's rite stopped managing this file
    if not stale:
        return

    print("Pruning stale manifest entries:")
    affected_tools: set[str] = set()
    for key in sorted(stale):
        tool, filename = key.split("/", 1)
        tome_file = tome_root / tool / filename
        print(f"  - {key}")
        del manifest[key]
        try:
            if tome_file.is_symlink() or tome_file.exists():
                tome_file.unlink()
        except OSError as e:
            print(f"    (could not remove tome file: {e})", file=sys.stderr)
        affected_tools.add(tool)

    # If a pruned tool's tome dir is now empty, drop it too.
    for tool in affected_tools:
        tome_tool_dir = tome_root / tool
        if tome_tool_dir.is_dir():
            try:
                tome_tool_dir.rmdir()  # fails if non-empty; that's fine
                print(f"  (removed empty tome/{tool}/)")
            except OSError:
                pass

    # Flag possible dangling symlinks for fully-removed tools.
    gone = sorted(t for t in affected_tools if t not in extant_tools)
    if gone:
        print(
            f"  note: symlinks previously created by "
            f"{', '.join(gone)} may now be dangling — "
            f"remove manually if no longer needed."
        )

    save_manifest(tome_root, manifest)
