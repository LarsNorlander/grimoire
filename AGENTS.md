# Grimoire Agent Notes

Grimoire is a personal macOS-only machine/config manager. Keep changes focused and preserve its architectural bets rather than making it portable.

## Boundaries

- macOS only. Do not add Linux/cross-platform gating to rites or runes.
- Nix is managed through nix-darwin on aarch64-darwin; Homebrew is an intentional escape hatch for GUI apps and fast-cadence tools.
- Do not store secrets in this repository. Secrets belong in 1Password.

## Architecture

- `grimoire` is the thin bash wrapper: ensure Nix/uv/Python are available, then delegate.
- `arcana/` owns CLI behavior and shared rite machinery.
- `rites/<tool>/rite.py` is a module exposing `rite(ctx: RiteContext)`, which registers the tool's managed files; keep tool-specific logic in the rite, not the wrapper. To park a rite, rename the file.
- `runes/` owns nix-darwin system configuration.
- `tome/` is gitignored build output. Symlinks should point to `tome/`, never directly to tracked rite sources.

## Rite conventions

- Prefer `ctx.copy()` for source files edited directly.
- Use `ctx.write()` for generated/merged content; builders receive `profile`, `rite_dir`, and `grimoire_root`.
- Use `ctx.link()` for managed symlinks and `ctx.hook()` only for necessary imperative setup.
- Use `ctx.patch()` when only some keys of a JSON file should be managed (the tool rewrites the rest itself). The fragment's leaves are owned; arrays are leaves. No `link()` — the target is written in place.
- Profile gating belongs in rite header comments (`# profile: ...`), not in runtime branches.
- `grimoire accept` round-trips `copy()` files and the owned keys of `patch()` files; generated files need manual reconciliation.

## Development notes

- Python version and dependencies are authoritative in `pyproject.toml`.
- Run the tests with `uv run python -m unittest discover -s tests`. They drive the CLI against a temp root via the `GRIMOIRE_ROOT` and `GRIMOIRE_PROFILE_FILE` env overrides; never against `~/.grimoire`.
- Scripts (`grimoire`, cantrips) use shebangs, have no file extensions, and are executable. Rites are modules, not scripts.
- Keep README aligned with user-visible behavior changes, but avoid duplicating `--help` output or exhaustive file lists.
- Before committing, check staged changes for secrets, credentials, tokens, and private keys.
