# Grimoire

Personal machine configuration and scripts, portable across work and personal Macs.

## Architecture

Three layers with strict responsibilities:

- **`arcana/`** — pure library code, no entry points. Provides `RiteContext` which is mode-aware: the same rite script works in build mode and accept mode because the context changes behavior, not the script.
- **`rites/*/rite`** — each rite is a self-contained executable that manages its tool's files using `RiteContext` operations. A single rite can mix `copy()` (source files in the rite dir) and `write()` (generated content) — the distinction is per-file, not per-rite. Arbitrary Python logic (merging, templating) can happen between calls. New modes are handled by `RiteContext`, not by changing rite scripts.
- **`cast`** — orchestrator only. Handles prerequisites, profile, and dispatches to rite scripts with the right flags. If `cast` needs a separate script to do something, the responsibility is probably in the wrong place — it should be in the rite or in arcana.

`cast` orchestrates the full deployment:

1. **Nix** — ensures Nix (Determinate) is installed, sources the daemon profile
2. **Profile** — prompts for `work` or `personal` on first run, stores in `~/.grimoire-profile` (`--recast` re-prompts)
3. **Grimoire symlink** — links `~/.grimoire` to the repo (if not cloned there)
4. **Runes** — runs `darwin-rebuild switch` with the profile-appropriate flake output (installs packages, casks, fonts, macOS defaults)
5. **Prerequisites** — ensures `uv` is available (installed by runes), syncs `.venv` from `pyproject.toml` if `uv.lock` is newer
6. **Rites** — runs each `rites/*/rite` script with the profile, outputting to `tome/` and symlinking to expected locations

Flags: `--recast` (re-prompt profile), `--force` (overwrite externally modified tome files), `--accept <tool>` (copy external changes back into rite sources), `--help`/`-h`.

## Directory Layout

- `arcana/` — pure Python library for rite scripts. No executables — only imported by rites.
- `runes/` — nix-darwin system configuration. `flake.nix` defines personal and work outputs; `configuration.nix` is the shared base; `personal.nix` and `work.nix` are profile overlays.
- `rites/<tool>/` — source files and a `rite` script per tool. The rite script receives `<profile> <grimoire_root>` as args, writes to `tome/`, and creates symlinks via `ctx.link()`.
- `cantrips/` — standalone executable scripts. Available at `~/.grimoire/cantrips/` after cast.
- `tome/` — gitignored. Contains built config files ready for symlinking.
- `.venv/` — gitignored. Managed by uv from `pyproject.toml`.

## Adding a New Config

1. Create `rites/<tool>/` with source files and a `rite` script (must be `chmod +x`)
2. For simple copy configs:
   ```python
   #!/usr/bin/env python3
   from arcana.tome import RiteContext
   ctx = RiteContext.from_args()
   ctx.copy("filename")
   ctx.link("filename", "~/.config/tool/filename")
   ```
3. For generated configs, pass a builder function to `ctx.write()`:
   ```python
   def build_config(*, profile, rite_dir, **_):
       # load, merge, template — return content as string
       return result

   ctx = RiteContext.from_args()
   ctx.write("config.toml", build_config)
   ctx.link("config.toml", "~/.config/tool/config.toml")
   ```
   The builder receives `profile`, `rite_dir`, and `grimoire_root` as kwargs. It is never called in accept mode.
4. Update `README.md` — add the rite to the structure tree and the "What Gets Managed" rites table.

**Accept mode note:** `--accept` only round-trips `copy()`-managed files (copies the tome file back into the rite source dir). For `write()`-managed files, accept warns and skips — you must manually reconcile generated content.

## README Consistency

After any structural change (adding/removing rites, cantrips, runes packages, cast flags, or altering how cast works), read `README.md` and verify these sections still match reality:
- The directory structure tree
- The rites table in "What Gets Managed"
- Profile-specific package lists (Nix packages, Homebrew formulae, casks)
- Cast step descriptions and flags
Fix any inconsistencies before committing.

## Commit Safety

Before committing, always check that no secrets, credentials, tokens, API keys, or other sensitive data are included in the staged changes. This repo should never contain secrets — they belong in 1Password.

## Conventions

- Python `>=3.14`, with `tomlkit` as the only external dependency (declared in `pyproject.toml`)
- Rite scripts are Python, invoked via the `run_arcana` helper in `cast`: `(cd "$grimoire_root" && PYTHONPATH="$grimoire_root" uv run "$@")`
- `cast` is bash — it handles system-level bootstrapping before Python is available
- Profiles: `work` adds work-specific config (e.g. extra AeroSpace workspaces), `personal` is the base
- Config merging: base files are the complete personal config; overlay files add to it. Arrays concatenate, dicts merge recursively.
- Scripts follow the shebang convention — no file extensions, `chmod +x`
- All symlinks point to `tome/` (gitignored), never to source files — protects tracked files from tools that auto-modify their config
- A manifest (`tome/.manifest`) tracks content hashes of built files. If a tome file is externally modified, `cast` warns and skips it. Use `--force` to overwrite, or `--accept <tool>` to copy changes back into rite sources. Accept only round-trips `copy()`-managed files — `write()`-managed files warn that they need manual reconciliation.

## Key Files

| File | Purpose |
|---|---|
| `cast` | Bash bootstrap: sources nix, delegates to `arcana/cli.py` |
| `arcana/cli.py` | Python CLI: profile, runes, prerequisites, rites dispatch |
| `pyproject.toml` | uv project config, declares Python dependencies |
| `arcana/tome.py` | Shared `RiteContext` class for rite scripts |
| `runes/flake.nix` | Nix flake entrypoint (personal + work outputs) |
| `runes/configuration.nix` | Shared nix-darwin base (packages, casks, fonts, macOS defaults) |
| `runes/personal.nix` | Personal profile overlay (julia via Homebrew) |
| `runes/work.nix` | Work profile overlay (awscli2, gh, golangci-lint, jq, kubectl via Nix; mysql-client via Homebrew; typora via cask) |
| `rites/aerospace/rite` | Merges base.toml + profile overlay → tome/aerospace/aerospace.toml |
| `rites/aerospace/base.toml` | Shared AeroSpace config (all profiles) |
| `rites/aerospace/work.toml` | Work-only overlay (Dia, Slack, Notion workspaces) |
| `rites/aerospace/personal.toml` | Personal-only overlay (Chrome on alt-4, Discord on alt-5) |
