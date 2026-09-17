#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import click

from arcana import diff as diff_mod
from arcana import docs as docs_mod
from arcana import rites as rites_mod
from arcana.rites import VALID_PROFILES, RiteNotFound
from arcana.manifest import Manifest
from arcana.tome import RiteSkipped

sys.dont_write_bytecode = True  # rite scripts are extension-less; no point caching

# The bash wrapper guarantees ~/.grimoire points at the checkout, so that is
# the default. The env overrides exist so tests (and ad-hoc checks) can aim
# the CLI at a throwaway root and profile without touching the real machine.
GRIMOIRE_ROOT = Path(os.environ.get("GRIMOIRE_ROOT") or Path.home() / ".grimoire")
PROFILE_FILE = Path(os.environ.get("GRIMOIRE_PROFILE_FILE") or Path.home() / ".grimoire-profile")
# The code checkout: where pyproject.toml and the venv live. Usually the same
# directory as GRIMOIRE_ROOT, but not when a test aims the root elsewhere.
CHECKOUT = Path(__file__).resolve().parents[1]

# Where `scribe` writes when nothing overrides it. This is homepage's own
# default content directory — `os.UserConfigDir()/homepage/content` with one
# subdirectory per kind — so a fresh machine needs no configuration on either
# side to make generated sheets show up.
# Stamped into every sheet, and the marker that makes a sheet ours to
# overwrite or prune in a directory we share with hand-written ones.
GENERATOR = "grimoire scribe"
SCRIBE_OUTPUT_ENV = "GRIMOIRE_SCRIBE_OUTPUT"
DEFAULT_SCRIBE_OUTPUT = (
    Path.home() / "Library" / "Application Support" / "homepage"
    / "content" / "cheatsheets"
)


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


def _is_ours(sheet: Path) -> bool:
    """Whether grimoire may write over this sheet.

    True when the file doesn't exist yet or carries our `generator` stamp. The
    output directory is shared with hand-written sheets, and clobbering one
    would destroy content no rite can regenerate.
    """
    if not sheet.exists():
        return True
    try:
        existing = json.loads(sheet.read_text())
    except (OSError, ValueError):
        return False
    return isinstance(existing, dict) and existing.get("generator") == GENERATOR


def _resolve_scribe_output(output: Path | None) -> Path:
    """Where scribe writes: --output, then $GRIMOIRE_SCRIBE_OUTPUT, then default.

    The env var is the configuration point, which means the zsh rite can export
    it and the override becomes grimoire-managed like everything else.
    """
    if output is not None:
        return output.expanduser()
    if configured := os.environ.get(SCRIBE_OUTPUT_ENV, "").strip():
        return Path(configured).expanduser()
    return DEFAULT_SCRIBE_OUTPUT


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
    venv_dir = CHECKOUT / ".venv"
    lock_file = CHECKOUT / "uv.lock"

    if (
        venv_dir.exists()
        and lock_file.exists()
        and not (lock_file.stat().st_mtime > venv_dir.stat().st_mtime)
    ):
        return

    click.echo("Checking prerequisites...")
    subprocess.run(["uv", "sync", "--quiet"], cwd=CHECKOUT, check=True)
    venv_dir.touch()
    click.echo("  Dependencies: ok\n")


def _rites_or_exit(tools: tuple[str, ...]) -> list[Path]:
    """Resolve named rites (or all), exiting with the CLI's error style if one is missing."""
    try:
        return rites_mod.discover(GRIMOIRE_ROOT, tools)
    except RiteNotFound as e:
        sys.exit(f"  ERROR: {e}")


def _cast(profile: str, *, force: bool, dry_run: bool = False,
          tools: tuple[str, ...] = ()) -> None:
    """Run build_rites and turn its failures into CLI output and exit status."""
    try:
        errors = rites_mod.build_rites(GRIMOIRE_ROOT, profile, force=force,
                                       dry_run=dry_run, tools=tools)
    except RiteNotFound as e:
        sys.exit(f"  ERROR: {e}")
    if errors:
        for tool, err in errors:
            click.echo(f"  ERROR in {tool}: {err}", err=True)
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _complete_tool_names(ctx, param, incomplete: str) -> list[str]:
    """Shell-completion callback: enumerate rites/*/rite.py as candidates.

    If a profile is set, filters out rites whose `# profile:` frontmatter
    excludes it. Reads the same directive `rites.load_rite` checks at runtime,
    so completion and execution never disagree.
    """
    current: str | None = None
    if PROFILE_FILE.exists():
        p = PROFILE_FILE.read_text().strip()
        if p in VALID_PROFILES:
            current = p
    return [
        rp.parent.name for rp in rites_mod.discover(GRIMOIRE_ROOT)
        if rp.parent.name.startswith(incomplete)
        and (current is None or rites_mod.allowed_under(rp, current))
    ]


def _complete_familiar_names(ctx, param, incomplete: str) -> list[str]:
    """Shell-completion callback: enumerate familiars/*.nix as candidates."""
    familiars_dir = GRIMOIRE_ROOT / "familiars"
    if not familiars_dir.is_dir():
        return []
    return sorted(
        p.stem for p in familiars_dir.glob("*.nix")
        if p.stem.startswith(incomplete)
    )


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
    _cast(profile, force=force, dry_run=dry_run, tools=tools)
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
    """Pull external changes back into rite sources (copy() files and patch() keys)."""
    click.echo(f"Accepting external changes ({GRIMOIRE_ROOT})\n")
    profile = _resolve_profile()
    click.echo()
    _ensure_prerequisites()
    for path in _rites_or_exit(tools):
        rites_mod.run_rite(path, profile, GRIMOIRE_ROOT,
                           force=False, accepting=True, dry_run=dry_run)
    click.echo("\nDone.")


# Ephemeral invocation ────────────────────────────────────────────────────────

@grimoire.command()
@click.argument("familiar", shell_complete=_complete_familiar_names)
@click.argument("cmd", nargs=-1, type=click.UNPROCESSED)
def summon(familiar: str, cmd: tuple[str, ...]) -> None:
    """Enter an ephemeral shell with the named familiar's tools.

    Pass a command after `--` to run it inside the familiar and exit:

        grimoire summon aws -- aws s3 ls
    """
    familiar_path = GRIMOIRE_ROOT / "familiars" / f"{familiar}.nix"
    if not familiar_path.is_file():
        sys.exit(
            f"ERROR: no familiar named '{familiar}' "
            f"(see {GRIMOIRE_ROOT}/familiars/)"
        )

    args = ["nix", "develop", "-f", str(familiar_path)]
    if cmd:
        args += ["--command", *cmd]
    else:
        # `nix develop` defaults to bash — hand off to the user's login
        # shell instead, so zsh/starship/aliases survive into the familiar.
        # The shellHook has already run by the time this shell starts, so
        # GRIMOIRE_FAMILIAR + other env vars are inherited.
        if user_shell := os.environ.get("SHELL"):
            args += ["--command", user_shell]

    result = subprocess.run(args)
    sys.exit(result.returncode)


# Compound verb ───────────────────────────────────────────────────────────────

@grimoire.command()
def bootstrap() -> None:
    """Provision a fresh machine: apply runes, then apply all rites."""
    click.echo(f"Bootstrapping grimoire from {GRIMOIRE_ROOT}\n")
    profile = _resolve_profile()
    click.echo()
    _apply_runes(profile)
    _ensure_prerequisites()
    _cast(profile, force=False)
    click.echo("Done.")


@grimoire.command()
@click.argument("tools", nargs=-1, metavar="[TOOL ...]",
                shell_complete=_complete_tool_names)
@click.option("--output", "-o", "output", type=click.Path(file_okay=False, path_type=Path),
              default=None,
              help=f"Directory to write JSON into. Defaults to ${SCRIBE_OUTPUT_ENV} "
                   "if set, otherwise homepage's content directory.")
def scribe(tools: tuple[str, ...], output: Path | None) -> None:
    """Generate cheatsheet data from the rites that document themselves.

    Writes one JSON file per documented tool, conforming to homepage's
    cheatsheet schema. Grimoire produces the data; homepage renders it.

    Read-only with respect to the machine: rites are loaded so their doc
    content registers, but no tome file is written and no symlink is touched.

    Writes to homepage's content directory by default. Override for one run
    with --output, or for good by exporting $GRIMOIRE_SCRIBE_OUTPUT.
    """
    click.echo(f"Scribing grimoire from {GRIMOIRE_ROOT}\n")
    profile = _resolve_profile()
    click.echo()
    _ensure_prerequisites()

    out_dir = _resolve_scribe_output(output)

    rite_paths = _rites_or_exit(tools)

    click.echo("Scribing sheets...")
    pages: list[tuple[str, docs_mod.DocPage]] = []
    errors: list[tuple[str, str]] = []

    for rite_path in rite_paths:
        tool = rite_path.parent.name
        try:
            ctx = rites_mod.load_rite(rite_path, profile, GRIMOIRE_ROOT)
            rite_pages = ctx.registered_docs()
        except RiteSkipped as e:
            click.echo(e)
            continue
        except Exception as e:
            errors.append((tool, str(e)))
            continue
        for i, page in enumerate(rite_pages):
            if not page.populated():
                click.echo(f"  {tool}: no content — skipping")
                continue
            page.generator = GENERATOR
            # Validate before writing, not after: an invalid sheet is rejected
            # outright by homepage's reader, so emitting one would replace a
            # good file with one that shows up as an error on the index.
            if found := docs_mod.problems(page):
                errors.append((tool, "\n".join(f"    {p}" for p in found)))
                continue
            filename = f"{tool}.json" if i == 0 else f"{tool}-{i}.json"
            pages.append((filename, page))

    out_dir.mkdir(parents=True, exist_ok=True)
    written_pages: list[tuple[str, docs_mod.DocPage]] = []
    for filename, page in pages:
        target = out_dir / filename
        if not _is_ours(target):
            errors.append((page.title, f"    {target} already exists and wasn't "
                                       f"written by {GENERATOR} — refusing to "
                                       f"overwrite it"))
            continue
        target.write_text(docs_mod.dumps(page))
        written_pages.append((filename, page))
        click.echo(f"  wrote {filename} — {len(page.populated())} sections, "
                   f"{page.entry_count()} bindings")
    pages = written_pages

    # Prune sheets whose rite stopped documenting itself. The output directory
    # is shared — homepage pools generated sheets with hand-written ones — so
    # ownership is read out of each file's own `generator` field rather than
    # assumed from the directory. Anything grimoire didn't write is left alone.
    # Skipped on a filtered run, which knows nothing about the tools it didn't
    # load and would prune every sheet it wasn't asked for.
    if not tools:
        written = {fn for fn, _ in pages}
        for sheet in sorted(out_dir.glob("*.json")):
            if sheet.name in written:
                continue
            if _is_ours(sheet):
                sheet.unlink()
                click.echo(f"  pruned {sheet.name} (no longer documented)")

    click.echo(f"\n{len(pages)} sheet(s) in {out_dir}")
    if errors:
        click.echo()
        for tool, err in errors:
            click.echo(f"  ERROR in {tool}: {err}", err=True)
        sys.exit(1)
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

    try:
        rite_paths = rites_mod.discover(GRIMOIRE_ROOT, (tool,) if tool else ())
    except RiteNotFound as e:
        click.echo(f"ERROR: {e}", err=True)
        cli_ctx.exit(2)

    manifest = Manifest.load(GRIMOIRE_ROOT / "tome")
    results = []
    errors: list[tuple[str, Exception]] = []
    for rite_path in rite_paths:
        try:
            ctx = rites_mod.load_rite(rite_path, profile, GRIMOIRE_ROOT)
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
