# Grimoire

Personal machine configuration and scripts, portable across work and personal Macs.

## Architecture

`cast` is the entry point. It orchestrates the full deployment:

1. **Prerequisites** — ensures Homebrew and uv are installed
2. **Profile** — prompts for `work` or `personal` on first run, stores in `~/.grimoire-profile`
3. **Build** — runs each `spells/*/build` script with the profile, outputting to `tome/`
4. **Symlinks** — links `~/.grimoire` to the repo (if not cloned there) and built configs to their expected locations

## Directory Layout

- `spells/<tool>/` — source files and a `build` script per tool. The build script receives `<profile> <grimoire_root>` as args and writes to `tome/`.
- `spells/arcana/` — shared Python library for build scripts. Provides `BuildContext` for args parsing, paths, and common operations like copying files to tome.
- `scripts/` — standalone executable scripts. Available at `~/.grimoire/scripts/` after cast.
- `tome/` — gitignored. Contains built config files ready for symlinking.
- `.venv/` — gitignored. Managed by uv from `pyproject.toml`.

## Adding a New Config

1. Create `spells/<tool>/` with source files and an executable `build` script
2. For simple copy configs:
   ```python
   #!/usr/bin/env python3
   from arcana.tome import BuildContext
   ctx = BuildContext.from_args()
   ctx.copy("filename")
   ```
3. For configs with profile-dependent merging, use `ctx.profile` and `ctx.spell_dir` to load and merge sources
4. Add the symlink to `cast`'s `create_symlinks()` function

## Conventions

- Build scripts are Python, run via `uv run` with `PYTHONPATH` set to `spells/`
- `cast` is bash — it handles system-level bootstrapping before Python is available
- Profiles: `work` adds work-specific config (e.g. extra AeroSpace workspaces), `personal` is the base
- Config merging: base files are the complete personal config; overlay files add to it. Arrays concatenate, dicts merge recursively.
- Scripts follow the shebang convention — no file extensions, `chmod +x`
- All symlinks point to `tome/` (gitignored), never to source files — protects tracked files from tools that auto-modify their config

## Key Files

| File | Purpose |
|---|---|
| `cast` | Deployment orchestrator (bash) |
| `pyproject.toml` | uv project config, declares Python dependencies |
| `spells/arcana/tome.py` | Shared `BuildContext` class for build scripts |
| `spells/aerospace/build` | Merges base.toml + work.toml → tome/aerospace/aerospace.toml |
| `spells/aerospace/base.toml` | Shared AeroSpace config (all profiles) |
| `spells/aerospace/work.toml` | Work-only overlay (Dia, Slack, Notion workspaces) |
