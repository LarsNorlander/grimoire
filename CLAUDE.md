# Grimoire

Personal machine configuration and scripts, portable across work and personal Macs.

## Architecture

`cast` is the entry point. It orchestrates the full deployment:

1. **Prerequisites** — ensures Homebrew and uv are installed
2. **Profile** — prompts for `work` or `personal` on first run, stores in `~/.grimoire-profile`
3. **Grimoire symlink** — links `~/.grimoire` to the repo (if not cloned there)
4. **Rites** — runs each `rites/*/rite` script with the profile, outputting to `tome/` and symlinking to expected locations

## Directory Layout

- `arcana/` — shared Python library for rite scripts. Provides `BuildContext` for args parsing, paths, and common operations like copying files to tome.
- `rites/<tool>/` — source files and a `rite` script per tool. The rite script receives `<profile> <grimoire_root>` as args, writes to `tome/`, and creates symlinks via `ctx.link()`.
- `cantrips/` — standalone executable scripts. Available at `~/.grimoire/cantrips/` after cast.
- `tome/` — gitignored. Contains built config files ready for symlinking.
- `.venv/` — gitignored. Managed by uv from `pyproject.toml`.

## Adding a New Config

1. Create `rites/<tool>/` with source files and an executable `rite` script
2. For simple copy configs:
   ```python
   #!/usr/bin/env python3
   from arcana.tome import BuildContext
   ctx = BuildContext.from_args()
   ctx.copy("filename")
   ctx.link("filename", "~/.config/tool/filename")
   ```
3. For configs with profile-dependent merging, use `ctx.profile` and `ctx.rite_dir` to load and merge sources, then `ctx.write()` and `ctx.link()`

## Conventions

- Rite scripts are Python, run via `uv run` with `PYTHONPATH` set to the grimoire root
- `cast` is bash — it handles system-level bootstrapping before Python is available
- Profiles: `work` adds work-specific config (e.g. extra AeroSpace workspaces), `personal` is the base
- Config merging: base files are the complete personal config; overlay files add to it. Arrays concatenate, dicts merge recursively.
- Scripts follow the shebang convention — no file extensions, `chmod +x`
- All symlinks point to `tome/` (gitignored), never to source files — protects tracked files from tools that auto-modify their config
- A manifest (`tome/.manifest`) tracks content hashes of built files. If a tome file is externally modified, `cast` warns and skips it. Use `--force` to overwrite, or `--accept <tool>` to copy changes back into rite sources (copy-based rites only).

## Key Files

| File | Purpose |
|---|---|
| `cast` | Deployment orchestrator (bash) |
| `pyproject.toml` | uv project config, declares Python dependencies |
| `arcana/tome.py` | Shared `BuildContext` class for rite scripts |
| `rites/aerospace/rite` | Merges base.toml + work.toml → tome/aerospace/aerospace.toml |
| `rites/aerospace/base.toml` | Shared AeroSpace config (all profiles) |
| `rites/aerospace/work.toml` | Work-only overlay (Dia, Slack, Notion workspaces) |
