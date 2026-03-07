# Grimoire

Personal machine configuration and scripts, portable across work and personal Macs.

## Architecture

`cast` is the entry point. It orchestrates the full deployment:

1. **Prerequisites** — ensures Homebrew and uv are installed
2. **Profile** — prompts for `work` or `personal` on first run, stores in `~/.grimoire-profile`
3. **Build** — runs each `config/*/build` script with the profile, outputting to `tome/`
4. **Symlinks** — links `~/.grimoire` to the repo (if not cloned there) and built configs to their expected locations

## Directory Layout

- `config/<tool>/` — source fragments and a `build` script per tool. The build script receives `<profile> <grimoire_root>` as args and writes to `tome/`.
- `scripts/` — standalone executable scripts. Available at `~/.grimoire/scripts/` after cast.
- `tome/` — gitignored. Contains built config files ready for symlinking.
- `.venv/` — gitignored. Managed by uv from `pyproject.toml`.

## Adding a New Config

1. Create `config/<tool>/` with source files and an executable `build` script
2. The build script should: read source files, merge based on profile, write to `tome/<filename>`
3. Add the symlink to `cast`'s `create_symlinks()` function

## Conventions

- Build scripts are Python, run via `uv run` (has access to dependencies in pyproject.toml)
- `cast` is bash — it handles system-level bootstrapping before Python is available
- Profiles: `work` adds work-specific config (e.g. extra AeroSpace workspaces), `personal` is the base
- Config merging: base.toml is the complete personal config; overlay files add to it. Arrays concatenate, dicts merge recursively.
- Scripts follow the shebang convention — no file extensions, `chmod +x`

## Key Files

| File | Purpose |
|---|---|
| `cast` | Deployment orchestrator (bash) |
| `pyproject.toml` | uv project config, declares Python dependencies |
| `config/aerospace/build` | Merges base.toml + work.toml → tome/aerospace.toml |
| `config/aerospace/base.toml` | Shared AeroSpace config (all profiles) |
| `config/aerospace/work.toml` | Work-only overlay (Dia, Slack, Notion workspaces) |
