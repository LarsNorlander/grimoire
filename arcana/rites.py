"""Discovering, loading, and running rites against a grimoire root.

The CLI parses arguments and prints; this module does the work, with the
root passed in explicitly so nothing here knows where the checkout lives.
Progress lines go to stdout the same way `RiteContext` reports its ops, so a
cast reads as one stream.
"""

import importlib.util
import sys
from pathlib import Path

from arcana.manifest import Manifest
from arcana.tome import RiteContext, RiteSkipped, parse_rite_profiles

VALID_PROFILES = ("work", "personal")


class RiteNotFound(Exception):
    def __init__(self, tool: str):
        super().__init__(f"no rite found for '{tool}'")
        self.tool = tool


def rite_path(root: Path, tool: str) -> Path:
    return root / "rites" / tool / "rite.py"


def discover(root: Path, tools: tuple[str, ...] = ()) -> list[Path]:
    """Rite scripts to operate on.

    Named tools must exist (``RiteNotFound`` otherwise). With no names, every
    ``rites/*/rite.py`` in sorted order. To park a rite, rename the file.
    """
    if tools:
        paths = []
        for tool in tools:
            path = rite_path(root, tool)
            if not path.is_file():
                raise RiteNotFound(tool)
            paths.append(path)
        return paths
    return sorted(root.glob("rites/*/rite.py"))


def allowed_under(path: Path, profile: str) -> bool:
    """Whether a rite's `# profile:` directive admits this profile."""
    allowed = parse_rite_profiles(path)
    return allowed is None or profile in allowed


def load_rite(path: Path, profile: str, root: Path, *,
              force: bool = False, accepting: bool = False) -> RiteContext:
    """Import a rite module and call its `rite(ctx)` to register ops.

    Honors `# profile: <names>` frontmatter — if the rite declares profile
    compatibility and we're not in accept mode, raises ``RiteSkipped`` before
    the module is imported. Accept mode bypasses the gate (you might want to
    salvage files from a work-profile rite while on personal).

    Nothing runs at import: a rite is a module with one function, so the
    context is passed in rather than fetched from shared state.
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
    spec = importlib.util.spec_from_file_location(f"grimoire.rites.{tool}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entry = getattr(module, "rite", None)
    if not callable(entry):
        raise TypeError(f"{path} must define rite(ctx)")
    ctx = RiteContext(profile, root, tool, force=force, accepting=accepting)
    entry(ctx)
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

    Symlinks the manifest recorded for a pruned file are removed too, but
    only while they still point at that tome file — a link the user has
    since repointed is theirs. A patch() target is a file the machine owns,
    so it is left in place and named in a note.
    """
    tome_root = root / "tome"
    manifest = Manifest.load(tome_root)
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
    untracked_links: list[str] = []
    for key in sorted(stale):
        tool, filename = key.split("/", 1)
        tome_file = tome_root / tool / filename
        print(f"  - {key}")
        entry = manifest.remove(key)
        for link in entry.links:
            _remove_link(Path(link), tome_file)
        if entry.target:
            print(f"    left {entry.target} in place — its keys are the machine's now")
        if entry.kind is None and not entry.links:  # pre-v2 entry: links unknown
            untracked_links.append(tool)
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

    # Entries migrated from the pre-v2 manifest carry no link list, so a
    # link they created can't be found — say so rather than stay silent.
    gone = sorted(t for t in set(untracked_links) if t not in extant_tools)
    if gone:
        print(
            f"  note: symlinks previously created by "
            f"{', '.join(gone)} may now be dangling — "
            f"remove manually if no longer needed."
        )

    manifest.save()


def _remove_link(link: Path, tome_file: Path) -> None:
    """Remove a symlink grimoire created, if it is still ours."""
    if not link.is_symlink():
        return
    if link.readlink() != tome_file:
        print(f"    kept {link} — no longer points at the tome file")
        return
    try:
        link.unlink()
        print(f"    removed {link}")
    except OSError as e:
        print(f"    (could not remove {link}: {e})", file=sys.stderr)
