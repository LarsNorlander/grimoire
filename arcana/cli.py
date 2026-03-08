#!/usr/bin/env python3
import os
import sys
import shutil
import subprocess
from pathlib import Path

import click

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


def _run_rite(rite_script: Path, profile: str, extra_flags: list[str]) -> None:
    env = {**os.environ, "PYTHONPATH": str(GRIMOIRE_ROOT)}
    subprocess.run(
        ["uv", "run", str(rite_script), profile, str(GRIMOIRE_ROOT)] + extra_flags,
        cwd=GRIMOIRE_ROOT,
        env=env,
        check=True,
    )


def _build_rites(profile: str, force: bool) -> None:
    click.echo("Building rites...")
    extra_flags = ["--force"] if force else []
    for rite_script in sorted(GRIMOIRE_ROOT.glob("rites/*/rite")):
        if not os.access(rite_script, os.X_OK):
            continue
        _run_rite(rite_script, profile, extra_flags)
    click.echo()


@click.command()
@click.option("--recast", is_flag=True, help="Re-prompt for machine profile.")
@click.option("--force", is_flag=True, help="Overwrite externally modified tome files.")
@click.option("--accept", multiple=True, metavar="TOOL", help="Accept external changes back into rite sources.")
def main(recast: bool, force: bool, accept: tuple[str, ...]) -> None:
    """Deploy grimoire onto the current machine."""
    if accept:
        _ensure_prerequisites()
        click.echo("Accepting external changes...")
        for tool in accept:
            rite_script = GRIMOIRE_ROOT / "rites" / tool / "rite"
            if not rite_script.is_file():
                sys.exit(f"  ERROR: no rite found for '{tool}'")
            _run_rite(rite_script, "", ["--accept"])
        click.echo("\nDone.")
        return

    click.echo(f"Casting grimoire from {GRIMOIRE_ROOT}\n")
    profile = _resolve_profile(recast)
    click.echo()
    _apply_runes(profile)
    _ensure_prerequisites()
    _build_rites(profile, force)
    click.echo("Done.")


if __name__ == "__main__":
    main(prog_name="cast")
