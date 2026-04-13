#!/usr/bin/env python3
import importlib.util
from importlib.machinery import SourceFileLoader
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

from arcana import diff as diff_mod
from arcana.tome import RiteContext, RiteSkipped, load_manifest

sys.dont_write_bytecode = True  # rite scripts are extension-less; no point caching

GRIMOIRE_ROOT = Path.home() / ".grimoire"
PROFILE_FILE = Path.home() / ".grimoire-profile"


def _resolve_profile(recast: bool) -> str:
    if PROFILE_FILE.exists() and not recast:
        profile = PROFILE_FILE.read_text().strip()
        click.echo(f"Profile: {profile} (from {PROFILE_FILE})")
        return profile

    is_work = click.confirm("Is this a work machine?", default=False)
    profile = "work" if is_work else "personal"
    PROFILE_FILE.write_text(profile + "\n")
    click.echo(f"Profile: {profile} (saved to {PROFILE_FILE})")
    return profile


def _apply_runes(profile: str) -> None:
    click.echo(f"Applying runes ({profile})...")
    flake = f"{GRIMOIRE_ROOT}/runes#{profile}"
    if shutil.which("darwin-rebuild"):
        subprocess.run(["sudo", "darwin-rebuild", "switch", "--flake", flake], check=True)
    else:
        subprocess.run(["sudo", "nix", "run", "nix-darwin", "--", "switch", "--flake", flake], check=True)
    os.environ["PATH"] = "/run/current-system/sw/bin:" + os.environ["PATH"]
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

    Returns the populated context. Raises ``RiteSkipped`` if the rite self-skipped
    via ``require_profile``; callers decide how to surface that.
    """
    tool = rite_path.parent.name
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


def _build_rites(profile: str, force: bool, dry_run: bool = False) -> None:
    click.echo("Building rites...")
    errors = []
    for rite_path in sorted(GRIMOIRE_ROOT.glob("rites/*/rite")):
        if not os.access(rite_path, os.X_OK):
            continue
        try:
            _run_rite(rite_path, profile, force=force, accepting=False, dry_run=dry_run)
        except Exception as e:
            errors.append((rite_path.parent.name, e))
    click.echo()
    if errors:
        for tool, err in errors:
            click.echo(f"  ERROR in {tool}: {err}", err=True)
        sys.exit(1)


@click.group()
def grimoire():
    """Grimoire — personal machine configuration manager."""
    pass


@grimoire.command()
@click.option("--recast", is_flag=True, help="Re-prompt for machine profile.")
@click.option("--force", is_flag=True, help="Overwrite externally modified tome files.")
@click.option("--accept", multiple=True, metavar="TOOL", help="Accept external changes back into rite sources.")
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes.")
@click.option("--only", type=click.Choice(["rites", "runes"]), default=None,
              help="Run only rites or runes (default: both).")
def cast(recast: bool, force: bool, accept: tuple[str, ...], dry_run: bool, only: str | None) -> None:
    """Deploy grimoire onto the current machine."""
    if accept:
        _ensure_prerequisites()
        click.echo("Accepting external changes...")
        for tool in accept:
            rite_path = GRIMOIRE_ROOT / "rites" / tool / "rite"
            if not rite_path.is_file():
                sys.exit(f"  ERROR: no rite found for '{tool}'")
            _run_rite(rite_path, "", force=False, accepting=True)
        click.echo("\nDone.")
        return

    click.echo(f"Casting grimoire from {GRIMOIRE_ROOT}\n")
    profile = _resolve_profile(recast)
    click.echo()
    if only != "rites":
        if not dry_run:
            _apply_runes(profile)
    if only != "runes":
        _ensure_prerequisites()
        _build_rites(profile, force, dry_run=dry_run)
    click.echo("Done.")


@grimoire.command()
@click.argument("tool", required=False)
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
        click.echo("ERROR: no profile set — run `grimoire cast` first.", err=True)
        cli_ctx.exit(2)
    profile = PROFILE_FILE.read_text().strip()

    if build:
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


if __name__ == "__main__":
    grimoire(prog_name="grimoire")
