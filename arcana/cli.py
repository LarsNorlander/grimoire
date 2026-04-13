#!/usr/bin/env python3
import importlib.util
from importlib.machinery import SourceFileLoader
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import click

from arcana import diff as diff_mod
from arcana.tome import (
    RiteContext,
    RiteSkipped,
    load_manifest,
    parse_rite_profiles,
    save_manifest,
)

sys.dont_write_bytecode = True  # rite scripts are extension-less; no point caching

GRIMOIRE_ROOT = Path.home() / ".grimoire"
PROFILE_FILE = Path.home() / ".grimoire-profile"
VALID_PROFILES = ("work", "personal")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_profile() -> str:
    if PROFILE_FILE.exists():
        profile = PROFILE_FILE.read_text().strip()
        if profile not in VALID_PROFILES:
            sys.exit(
                f"ERROR: {PROFILE_FILE} contains invalid profile '{profile}' "
                f"(expected one of: {', '.join(VALID_PROFILES)}).\n"
                f"       Fix with: grimoire profile set <work|personal>"
            )
        click.echo(f"Profile: {profile} (from {PROFILE_FILE})")
        return profile

    is_work = click.confirm("Is this a work machine?", default=False)
    profile = "work" if is_work else "personal"
    PROFILE_FILE.write_text(profile + "\n")
    click.echo(f"Profile: {profile} (saved to {PROFILE_FILE})")
    return profile


def _apply_runes(profile: str, dry_run: bool = False) -> None:
    verb = "Building" if dry_run else "Applying"
    suffix = " (dry-run — no activation)" if dry_run else ""
    click.echo(f"{verb} runes ({profile}){suffix}...")

    if dry_run:
        # For dry-run we only care whether the build succeeds. Bypass
        # `darwin-rebuild` (which doesn't forward `--no-link`) and call
        # `nix build` directly against the full flake attribute path.
        cmd = [
            "nix", "build",
            f"{GRIMOIRE_ROOT}/runes#darwinConfigurations.{profile}.system",
            "--no-link",
        ]
        subprocess.run(cmd, check=True)
    else:
        flake = f"{GRIMOIRE_ROOT}/runes#{profile}"
        if shutil.which("darwin-rebuild"):
            cmd = ["sudo", "darwin-rebuild", "switch", "--flake", flake]
        else:
            cmd = ["sudo", "nix", "run", "nix-darwin", "--", "switch", "--flake", flake]
        # `darwin-rebuild switch` writes a ./result symlink as a side effect.
        # Run in a tmpdir so the artifact doesn't pollute the invocation cwd.
        # The actual built store path is activated regardless.
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(cmd, check=True, cwd=tmpdir)
    click.echo()


def _ensure_prerequisites() -> None:
    venv_dir = GRIMOIRE_ROOT / ".venv"
    lock_file = GRIMOIRE_ROOT / "uv.lock"

    if (
        venv_dir.exists()
        and lock_file.exists()
        and not (lock_file.stat().st_mtime > venv_dir.stat().st_mtime)
    ):
        return

    click.echo("Checking prerequisites...")
    subprocess.run(["uv", "sync", "--quiet"], cwd=GRIMOIRE_ROOT, check=True)
    venv_dir.touch()
    click.echo("  Dependencies: ok\n")


def _load_rite(rite_path: Path, profile: str, *,
               force: bool = False, accepting: bool = False) -> RiteContext:
    """Execute a rite module so its ops register on a new RiteContext.

    Honors `# profile: <names>` frontmatter — if the rite declares profile
    compatibility and we're not in accept mode, raises ``RiteSkipped`` before
    the module is imported. Accept mode bypasses the gate (you might want to
    salvage files from a work-profile rite while on personal).
    """
    tool = rite_path.parent.name
    if not accepting:
        allowed = parse_rite_profiles(rite_path)
        if allowed:
            unknown = allowed - set(VALID_PROFILES)
            if unknown:
                click.echo(
                    f"  WARNING {tool}: unknown profile(s) in frontmatter: "
                    f"{', '.join(sorted(unknown))} "
                    f"(expected one of: {', '.join(VALID_PROFILES)})",
                    err=True,
                )
            if profile not in allowed:
                raise RiteSkipped(
                    f"  skipped {tool} — requires {'/'.join(sorted(allowed))} profile"
                )
    ctx = RiteContext(profile, GRIMOIRE_ROOT, tool, force=force, accepting=accepting)
    RiteContext._current = ctx
    try:
        spec = importlib.util.spec_from_file_location(
            "rite", rite_path, loader=SourceFileLoader("rite", str(rite_path))
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        RiteContext._current = None
    return ctx


def _run_rite(rite_path: Path, profile: str, force: bool, accepting: bool,
              dry_run: bool = False) -> None:
    try:
        ctx = _load_rite(rite_path, profile, force=force, accepting=accepting)
    except RiteSkipped as e:
        click.echo(e)
        return
    ctx.execute(dry_run=dry_run)


def _build_rites(profile: str, force: bool, dry_run: bool = False,
                 tools: tuple[str, ...] = ()) -> None:
    if tools:
        rite_paths = []
        for tool in tools:
            rite_path = GRIMOIRE_ROOT / "rites" / tool / "rite"
            if not rite_path.is_file():
                sys.exit(f"  ERROR: no rite found for '{tool}'")
            rite_paths.append(rite_path)
    else:
        rite_paths = sorted(GRIMOIRE_ROOT.glob("rites/*/rite"))

    click.echo("Building rites...")
    errors: list[tuple[str, Exception]] = []
    # Track keys owned by rites that ran this pass, so we can GC stale
    # manifest entries from tools that have stopped managing a file.
    touched: set[str] = set()
    built_tools: set[str] = set()
    for rite_path in rite_paths:
        if not os.access(rite_path, os.X_OK):
            continue
        try:
            ctx = _load_rite(rite_path, profile, force=force)
        except RiteSkipped as e:
            click.echo(e)
            continue
        except Exception as e:
            errors.append((rite_path.parent.name, e))
            continue
        built_tools.add(ctx.tool)
        touched.update(ctx.registered_keys())
        try:
            ctx.execute(dry_run=dry_run)
        except Exception as e:
            errors.append((rite_path.parent.name, e))
    click.echo()
    if errors:
        for tool, err in errors:
            click.echo(f"  ERROR in {tool}: {err}", err=True)
        sys.exit(1)

    # After a clean full rebuild, prune manifest entries whose rite stopped
    # managing them (or whose tool was removed entirely). Skipped rites (e.g.
    # profile-gated) are preserved — their entries are valid under the
    # matching profile.
    if not tools and not dry_run:
        _gc_manifest(touched, built_tools)


def _gc_manifest(touched: set[str], built_tools: set[str]) -> None:
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
    manifest = load_manifest(GRIMOIRE_ROOT / "tome")
    if not manifest:
        return
    tome_root = GRIMOIRE_ROOT / "tome"
    extant_tools = {
        rp.parent.name for rp in GRIMOIRE_ROOT.glob("rites/*/rite")
        if os.access(rp, os.X_OK)
    }
    stale: set[str] = set()
    for key in manifest:
        tool = key.split("/", 1)[0]
        if tool not in extant_tools:
            stale.add(key)  # tool removed entirely
        elif tool in built_tools and key not in touched:
            stale.add(key)  # tool's rite stopped managing this file
    if not stale:
        return

    click.echo("Pruning stale manifest entries:")
    affected_tools: set[str] = set()
    for key in sorted(stale):
        tool, filename = key.split("/", 1)
        tome_file = tome_root / tool / filename
        click.echo(f"  - {key}")
        del manifest[key]
        try:
            if tome_file.is_symlink() or tome_file.exists():
                tome_file.unlink()
        except OSError as e:
            click.echo(f"    (could not remove tome file: {e})", err=True)
        affected_tools.add(tool)

    # If a pruned tool's tome dir is now empty, drop it too.
    for tool in affected_tools:
        tome_tool_dir = tome_root / tool
        if tome_tool_dir.is_dir():
            try:
                tome_tool_dir.rmdir()  # fails if non-empty; that's fine
                click.echo(f"  (removed empty tome/{tool}/)")
            except OSError:
                pass

    # Flag possible dangling symlinks for fully-removed tools.
    gone = sorted(t for t in affected_tools if t not in extant_tools)
    if gone:
        click.echo(
            f"  note: symlinks previously created by "
            f"{', '.join(gone)} may now be dangling — "
            f"remove manually if no longer needed."
        )

    save_manifest(tome_root, manifest)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _complete_tool_names(ctx, param, incomplete: str) -> list[str]:
    """Shell-completion callback: enumerate rites/*/rite as candidates.

    If a profile is set, filters out rites whose `# profile:` frontmatter
    excludes it. Reads the same directive `_load_rite` checks at runtime,
    so completion and execution never disagree.
    """
    current: str | None = None
    if PROFILE_FILE.exists():
        p = PROFILE_FILE.read_text().strip()
        if p in VALID_PROFILES:
            current = p
    results: list[str] = []
    for rp in GRIMOIRE_ROOT.glob("rites/*/rite"):
        name = rp.parent.name
        if not name.startswith(incomplete) or not os.access(rp, os.X_OK):
            continue
        if current is not None:
            allowed = parse_rite_profiles(rp)
            if allowed and current not in allowed:
                continue
        results.append(name)
    return sorted(results)


@click.group()
def grimoire():
    """Grimoire — personal machine configuration manager."""
    pass


# Primitive action verbs ──────────────────────────────────────────────────────

@grimoire.command()
@click.argument("tools", nargs=-1, metavar="[TOOL ...]",
                shell_complete=_complete_tool_names)
@click.option("--force", is_flag=True, help="Overwrite externally modified tome files.")
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes.")
def cast(tools: tuple[str, ...], force: bool, dry_run: bool) -> None:
    """Apply rites to the current machine."""
    click.echo(f"Casting grimoire from {GRIMOIRE_ROOT}\n")
    profile = _resolve_profile()
    click.echo()
    _ensure_prerequisites()
    _build_rites(profile, force, dry_run=dry_run, tools=tools)
    click.echo("Done.")


@grimoire.command()
@click.option("--dry-run", is_flag=True,
              help="Build the nix-darwin configuration without activating it.")
def inscribe(dry_run: bool) -> None:
    """Apply runes (nix-darwin switch) to the current machine."""
    click.echo(f"Inscribing grimoire from {GRIMOIRE_ROOT}\n")
    profile = _resolve_profile()
    click.echo()
    _apply_runes(profile, dry_run=dry_run)
    click.echo("Done.")


@grimoire.command()
@click.argument("tools", nargs=-1, required=True, metavar="TOOL [TOOL ...]",
                shell_complete=_complete_tool_names)
@click.option("--dry-run", is_flag=True, help="Show what would be accepted without copying.")
def accept(tools: tuple[str, ...], dry_run: bool) -> None:
    """Pull external changes back into rite sources (copy()-managed files only)."""
    click.echo(f"Accepting external changes ({GRIMOIRE_ROOT})\n")
    profile = _resolve_profile()
    click.echo()
    _ensure_prerequisites()
    for tool in tools:
        rite_path = GRIMOIRE_ROOT / "rites" / tool / "rite"
        if not rite_path.is_file():
            sys.exit(f"  ERROR: no rite found for '{tool}'")
        _run_rite(rite_path, profile, force=False, accepting=True, dry_run=dry_run)
    click.echo("\nDone.")


# Compound verb ───────────────────────────────────────────────────────────────

@grimoire.command()
def bootstrap() -> None:
    """Provision a fresh machine: apply runes, then apply all rites."""
    click.echo(f"Bootstrapping grimoire from {GRIMOIRE_ROOT}\n")
    profile = _resolve_profile()
    click.echo()
    _apply_runes(profile)
    _ensure_prerequisites()
    _build_rites(profile, force=False)
    click.echo("Done.")


# Inspection ──────────────────────────────────────────────────────────────────

@grimoire.command()
@click.argument("tool", required=False, shell_complete=_complete_tool_names)
@click.option("--drift", "show_drift", is_flag=True,
              help="Show drift: tome vs. manifest (local edits since last cast).")
@click.option("--cast", "show_cast", is_flag=True,
              help="Show cast preview: fresh rebuild vs. current tome.")
@click.option("--accept", "show_accept", is_flag=True,
              help="Show accept preview: tome vs. rite source.")
@click.option("--build", is_flag=True,
              help="Run write() generators so --cast can evaluate them.")
@click.option("--full", is_flag=True,
              help="Show unified-diff content instead of a summary.")
@click.pass_context
def diff(cli_ctx: click.Context, tool: str | None,
         show_drift: bool, show_cast: bool, show_accept: bool,
         build: bool, full: bool) -> None:
    """Show how tome state differs from manifest, fresh rebuild, or rite sources."""
    if not PROFILE_FILE.exists():
        click.echo(
            "ERROR: no profile set — run `grimoire profile set <work|personal>` "
            "or `grimoire bootstrap`.", err=True)
        cli_ctx.exit(2)
    profile = PROFILE_FILE.read_text().strip()

    # Loading a rite imports its module, which may import nix-managed deps
    # (e.g. tomlkit). Ensure the venv is ready regardless of --build.
    _ensure_prerequisites()

    selected = {
        d for d, on in [
            (diff_mod.Direction.DRIFT, show_drift),
            (diff_mod.Direction.CAST, show_cast),
            (diff_mod.Direction.ACCEPT, show_accept),
        ]
        if on
    } or set(diff_mod.Direction)

    if tool:
        rite_path = GRIMOIRE_ROOT / "rites" / tool / "rite"
        if not rite_path.is_file():
            click.echo(f"ERROR: no rite for '{tool}'", err=True)
            cli_ctx.exit(2)
        rite_paths = [rite_path]
    else:
        rite_paths = sorted(GRIMOIRE_ROOT.glob("rites/*/rite"))

    manifest = load_manifest(GRIMOIRE_ROOT / "tome")
    results = []
    errors: list[tuple[str, Exception]] = []
    for rite_path in rite_paths:
        if not os.access(rite_path, os.X_OK):
            continue
        try:
            ctx = _load_rite(rite_path, profile)
        except RiteSkipped:
            continue
        except Exception as e:
            errors.append((rite_path.parent.name, e))
            continue
        for plan in diff_mod.plan_rite(ctx, build=build):
            results.append(diff_mod.compute_diff(plan, manifest, build))

    output = (
        diff_mod.format_full(results, selected)
        if full
        else diff_mod.format_summary(results, selected)
    )
    click.echo(output)

    if errors:
        click.echo()
        for tool_name, err in errors:
            click.echo(f"  ERROR in {tool_name}: {err}", err=True)
        cli_ctx.exit(2)

    any_changes = any(not r.is_clean_in(selected) for r in results)
    cli_ctx.exit(1 if any_changes else 0)


# Meta ────────────────────────────────────────────────────────────────────────

@grimoire.group(invoke_without_command=True)
@click.pass_context
def profile(cli_ctx: click.Context) -> None:
    """Show or change the machine profile (work/personal)."""
    if cli_ctx.invoked_subcommand is not None:
        return
    if PROFILE_FILE.exists():
        click.echo(PROFILE_FILE.read_text().strip())
    else:
        click.echo("(not set)")
        cli_ctx.exit(1)


@profile.command(name="set")
@click.argument("name", type=click.Choice(VALID_PROFILES))
def profile_set(name: str) -> None:
    """Set the machine profile to NAME."""
    PROFILE_FILE.write_text(name + "\n")
    click.echo(f"Profile set to {name} ({PROFILE_FILE})")


@profile.command(name="unset")
def profile_unset() -> None:
    """Clear the profile (next verb that needs one will prompt)."""
    if PROFILE_FILE.exists():
        PROFILE_FILE.unlink()
        click.echo(f"Profile cleared ({PROFILE_FILE} removed).")
    else:
        click.echo("Profile already unset.")


if __name__ == "__main__":
    grimoire(prog_name="grimoire")
