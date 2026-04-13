# Grimoire

Personal machine configuration and scripts, portable across work and personal Macs.

## Architecture

Three layers with strict responsibilities:

- **`arcana/`** — Python library and CLI entry point. Provides `RiteContext` which is mode-aware: the same rite script works in build mode and accept mode because the context changes behavior, not the script.
- **`rites/*/rite`** — each rite is a self-contained executable that manages its tool's files using `RiteContext` operations. A single rite can mix `copy()` (source files in the rite dir) and `write()` (generated content) — the distinction is per-file, not per-rite. Arbitrary Python logic (merging, templating) can happen between calls. New modes are handled by `RiteContext`, not by changing rite scripts.
- **`grimoire`** — orchestrator only. Handles prerequisites, profile, and dispatches to rite scripts with the right flags. If `grimoire` needs a separate script to do something, the responsibility is probably in the wrong place — it should be in the rite or in arcana.

The `grimoire` bash wrapper has one job: make sure Python can run. Specifically it:

1. **Sources Nix** — sources the daemon profile and prepends `/run/current-system/sw/bin` to PATH
2. **Installs Nix if missing** — via the Determinate Systems installer (interactive prompt)
3. **Creates `~/.grimoire` symlink** — so the Python CLI can rely on a stable path
4. **Ensures `uv` is available** — if `uv` isn't on PATH, execs Python inside `nix shell nixpkgs#uv` for that invocation. The `bootstrap` verb will install uv system-wide via `darwin-rebuild switch`, so subsequent invocations find it directly.

The bash wrapper does **not** prompt for profile or run `darwin-rebuild`; both belong to Python. Keeping bash minimal means the verb semantics live in one place.

The Python CLI exposes six verbs:

- **`grimoire bootstrap`** — compound verb for fresh-machine setup. Runs `_apply_runes` + `_build_rites` in one invocation. Idempotent.
- **`grimoire cast [TOOL ...]`** — apply rites. Optional positional args narrow to specific rites.
  Flags: `--force`, `--dry-run`.
- **`grimoire inscribe`** — apply runes (`darwin-rebuild switch` against the profile's flake output).
  Flags: `--dry-run` (uses `darwin-rebuild build` — materializes but does not activate).
- **`grimoire accept TOOL [TOOL ...]`** — pull external changes back into rite sources (`copy()`-managed files only).
  Flags: `--dry-run`.
- **`grimoire diff [TOOL]`** — inspect drift/cast/accept axes against the current tome.
  Flags: `--drift` / `--cast` / `--accept`, `--build`, `--full`.
- **`grimoire profile`** — show or change the machine profile (work/personal). Click group with subcommands `set NAME` and `unset`. Bare `grimoire profile` prints the current profile (exits 1 if unset).

Rites and runes are independent — to apply both without `bootstrap`, chain: `grimoire inscribe && grimoire cast`. `bootstrap` is just syntactic sugar for that composition.

Profile is the source of truth in `~/.grimoire-profile` (plain text, single line). The `profile` group is ergonomic UI on top — power users can edit the file directly. Verbs that need the profile read it via `_resolve_profile()`, which prompts interactively if the file is missing.

## Directory Layout

- `arcana/` — Python library and CLI entry point.
- `runes/` — nix-darwin system configuration. `flake.nix` defines personal and work outputs; `configuration.nix` is the shared base; `personal.nix` and `work.nix` are profile overlays.
- `rites/<tool>/` — source files and a `rite` script per tool. Each rite imports `RiteContext` and registers declarative ops (`copy`, `write`, `link`, `hook`); the CLI loads the rite module and executes the ops against `tome/`. Rites can also be invoked standalone for debugging: `./rites/<tool>/rite <profile> <grimoire_root> [--force] [--accept]`.
- `cantrips/` — standalone executable scripts. Always present at `~/.grimoire/cantrips/` (via the `~/.grimoire` symlink). On `PATH` after the zsh rite applies — so `grimoire cast` + a new shell makes them directly invocable.
- `tome/` — gitignored. Contains built config files ready for symlinking.
- `.venv/` — gitignored. Managed by uv from `pyproject.toml`.

## Adding a New Config

1. Create `rites/<tool>/` with source files and a `rite` script
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
4. For profile-gated configs, add a `# profile:` directive in the rite header:
   ```python
   #!/usr/bin/env python3
   # profile: work
   from arcana.tome import RiteContext
   ctx = RiteContext.from_args()
   ctx.copy("config.yml")
   ctx.link("config.yml", "~/.config/tool/config.yml")
   ```
   Space-separated for multiple profiles (`# profile: work personal`). Rites with no directive apply to every profile. The directive is the single source of truth: `_load_rite` raises `RiteSkipped` without importing the module if the current profile isn't in the allowed set, and shell-completion reads the same directive to filter incompatible rites from tab candidates. Accept mode bypasses the gate (to salvage files regardless of current profile).
5. Update `README.md` — add the rite to the structure tree.

**Accept mode note:** `grimoire accept` only round-trips `copy()`-managed files (copies the tome file back into the rite source dir). For `write()`-managed files, accept warns and skips — you must manually reconcile generated content.

## README Consistency

After any structural change (adding/removing rites, cantrips, subcommand flags, or altering how any verb works), read `README.md` and verify these sections still match reality:
- The directory structure tree
- Per-verb sections (`cast`, `inscribe`, `accept`, `diff`, `profile`) — descriptions and flags
Fix any inconsistencies before committing.

## Commit Safety

Before committing, always check that no secrets, credentials, tokens, API keys, or other sensitive data are included in the staged changes. This repo should never contain secrets — they belong in 1Password.

## Conventions

- Python `>=3.14`, with `click`, `detect-secrets`, and `tomlkit` as external dependencies (declared in `pyproject.toml`)
- Profiles: `work` adds work-specific config (e.g. extra AeroSpace workspaces), `personal` is the base
- Config merging: base files are the complete personal config; overlay files add to it. Arrays concatenate, dicts merge recursively.
- Scripts follow the shebang convention — no file extensions, `chmod +x`
- All symlinks point to `tome/` (gitignored), never to source files — protects tracked files from tools that auto-modify their config

## Key Files

| File | Purpose |
|---|---|
| `grimoire` | Bash wrapper: ensures nix + uv available, delegates to `arcana/cli.py` |
| `arcana/cli.py` | Python CLI: `bootstrap`, `cast`, `inscribe`, `accept`, `diff`, `profile` subcommands |
| `pyproject.toml` | uv project config, declares Python dependencies |
| `arcana/tome.py` | Shared `RiteContext` class for rite scripts |
| `runes/flake.nix` | Nix flake entrypoint (personal + work outputs) |
| `runes/configuration.nix` | Shared nix-darwin base (packages, casks, fonts, macOS defaults) |
| `runes/personal.nix` | Personal profile overlay (julia via Homebrew) |
| `runes/work.nix` | Work profile overlay (awscli2, gh, golangci-lint, jq, kubectl via Nix; mysql-client@8.4 via Homebrew; typora via cask) |
