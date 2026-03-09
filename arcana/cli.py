#!/usr/bin/env python3
import importlib.util
from importlib.machinery import SourceFileLoader
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

from arcana.tome import RiteContext, RiteSkipped

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


def _run_rite(rite_path: Path, profile: str, force: bool, accepting: bool,
              dry_run: bool = False) -> None:
    tool = rite_path.parent.name
    ctx = RiteContext(profile, GRIMOIRE_ROOT, tool, force=force, accepting=accepting)
    RiteContext._current = ctx
    try:
        spec = importlib.util.spec_from_file_location(
            "rite", rite_path, loader=SourceFileLoader("rite", str(rite_path))
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except RiteSkipped as e:
        click.echo(e)
        return
    finally:
        RiteContext._current = None
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
def cast(recast: bool, force: bool, accept: tuple[str, ...], dry_run: bool) -> None:
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
    if not dry_run:
        _apply_runes(profile)
    _ensure_prerequisites()
    _build_rites(profile, force, dry_run=dry_run)
    click.echo("Done.")


if __name__ == "__main__":
    grimoire(prog_name="grimoire")
