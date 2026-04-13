# Grimoire

Personal Mac configuration — what's installed and how tools are configured, portable across work and personal machines. (The fantasy naming is intentional: "rites" are config scripts, "runes" are Nix packages, "tome" is the build output; `grimoire cast` applies rites and `grimoire inscribe` applies runes.)

## Scope

Grimoire is a **macOS-only** configuration manager, by design. Its architecture is shaped by macOS conventions — `nix-darwin`, Homebrew as an escape hatch, `darwin-rebuild switch`, profile overlays that assume a desktop environment. Making it cross-platform would require hedging each of those choices, trading coherence for reach. Linux support is out of scope; a non-macOS machine warrants a separate tool with its own architectural bets, not an expansion of grimoire.

## Install

On a new machine, clone directly to `~/.grimoire` and invoke the bash wrapper by full path (it's not on `PATH` yet):

```
git clone git@github.com:LarsNorlander/grimoire.git ~/.grimoire
~/.grimoire/grimoire bootstrap
```

`bootstrap` is the end-to-end provisioning verb. The bash wrapper makes sure Nix and `uv` are available, then hands off to Python. `bootstrap` prompts for profile, applies runes (system packages, casks, fonts, macOS defaults via `darwin-rebuild switch`), then applies all rites. After the zsh rite runs, `~/.grimoire` is on `PATH`, so from the next shell onward you can use `grimoire` directly.

`bootstrap` is idempotent — safe to re-run. After the initial bootstrap, use the narrower verbs (`cast`, `inscribe`, `accept`, `diff`) for day-to-day work.

### `grimoire cast` — apply rites

Rites are the common case: every time you tweak a tool config, `cast` rebuilds the tome and refreshes symlinks. Pass tool names to narrow to specific rites; `--force` and `grimoire accept` cover drift resolution (see below). Run `grimoire cast --help` for the full flag reference.

### `grimoire inscribe` — apply runes

Runes are the system layer: packages, Homebrew casks, fonts, macOS defaults. Run `inscribe` after editing `runes/*.nix`. `--dry-run` materializes the derivation without activating.

### `grimoire profile` — show or change the machine profile

The profile is stored in `~/.grimoire-profile` and selects which flake output runes target and which overlay rites apply. `grimoire profile` alone prints the current profile; `grimoire profile set <name>` changes it, `unset` clears it.

### `grimoire summon` — invoke an ephemeral familiar

Familiars (`familiars/<name>.nix`) are named, ephemeral toolkits — each one a `mkShell` expression declaring packages and shell hooks. `grimoire summon <name>` drops you into a shell with those tools on `PATH` and the familiar's env vars set; exit and nothing persists in your home directory. Use them for tools you reach for rarely or for language experiments you don't want cluttering your daily environment.

Run a single command inside a familiar without entering the shell:

    grimoire summon aws -- aws s3 ls

Rule of thumb: if a tool's config lives in `~/.config/...` and you want it managed, that's a rite (persistent). If all you need is the binary on `PATH` plus env vars, it's a familiar.

## Structure

- `grimoire` — bash wrapper (sources Nix, ensures `uv`, delegates to the Python CLI)
- `arcana/` — Python library (`RiteContext`) and CLI entry point (`cli.py`)
- `runes/` — nix-darwin system config: a flake with one output per profile, a shared base, and per-profile overlays
- `rites/<tool>/` — one directory per managed tool, each with source files and a `rite` script
- `cantrips/<tool>/` — standalone utility scripts, organized by the tool they relate to
- `familiars/<name>.nix` — ephemeral toolkits (each a `mkShell` expression), summoned via `grimoire summon`
- `tome/` — gitignored build output (every symlink points here)
- `pyproject.toml` — Python dependencies (managed by uv)

Browse `rites/`, `cantrips/`, and `familiars/` to see what's currently managed — the directories are the source of truth, not this README.

## How It Works

Grimoire has three layers, each with a single job:

- **`arcana/`** — a Python library and CLI entry point. Provides `RiteContext`, which is the only API rite scripts need. The context is *mode-aware*: the same rite script works in build mode and accept mode because the context changes behavior, not the script. Rites never branch on mode.
- **`rites/*/rite`** — one self-contained executable per tool. Each rite describes *what* to build and where to link it, using two operations: `copy()` for static files and `write()` for generated content. A single rite can mix both — the distinction is per-file, not per-rite.
- **`grimoire`** — the orchestrator. A thin bash wrapper (ensures Nix is installed, manages the `~/.grimoire` symlink, makes `uv` available via `nix shell` on first run) that hands off to a Python CLI (`arcana/cli.py`) for profile selection, rune application, prerequisite sync, and rite dispatch. It doesn't know what any tool's config looks like.

### `copy()` vs `write()`

**`copy()`** is for files you edit directly. A minimal rite is three lines:

```python
ctx = RiteContext.from_args()
ctx.copy("config.toml")
ctx.link("config.toml", "~/.config/tool/config.toml")
```

**`write()`** takes a builder function for configs that need merging, templating, or any other transformation:

```python
def build_config(*, profile, rite_dir, **_):
    # load files from rite_dir, merge profile-aware, return a string
    ...

ctx = RiteContext.from_args()
ctx.write("config.toml", build_config)
ctx.link("config.toml", "~/.config/tool/config.toml")
```

The builder receives `profile`, `rite_dir`, and `grimoire_root` as kwargs — enough to load files and make profile-aware decisions. See `rites/` for concrete examples of both patterns.

### Drift detection

Symlinks always point to `tome/` (gitignored), so tools that auto-modify their config write to the build copy — tracked source files stay clean.

A manifest (`tome/.manifest`) tracks content hashes of every built file. If a tome file is externally modified, `grimoire cast` warns and skips it instead of silently overwriting your changes. From there:

- `grimoire cast --force` — overwrite and rebuild from source
- `grimoire accept <tool> [<tool2> ...]` — pull the external changes back into the rite's source directory (only works for `copy()`-managed files; `write()` files need manual reconciliation since they're generated)

### Inspecting drift

`grimoire diff [<tool>]` shows how the current tome state compares along three axes — by default all three are shown in summary form:

- **drift** — tome vs. manifest (what's changed on disk since last cast)
- **cast** — tome vs. what a fresh rebuild would produce (what `grimoire cast` would change)
- **accept** — tome vs. rite source (what `grimoire accept` would pull back; `copy()`-managed files only)

When the same file has both drift and pending cast changes, `diff` flags it as a potential conflict — both `cast --force` and `accept` would each clobber something.

Flags let you restrict to specific axes, re-run `write()` generators inline (`--build`), or print unified diffs (`--full`); see `grimoire diff --help` for the exact set. Exit codes: `0` no changes, `1` changes present, `2` error.

## Adding a New Config

Create `rites/<tool>/` with your source files and a `rite` script (`chmod +x`). Use `copy()` for static files or `write()` with a builder for generated ones (see [How It Works](#how-it-works) above). `grimoire cast` discovers the new rite automatically on the next run.

## Secrets

Secrets are managed through [1Password](https://1password.com/) and its CLI (`op`). Nothing sensitive is stored in this repo — credentials, tokens, and keys are referenced from 1Password at runtime.

## Contributing

This is a personal configuration repo — it reflects one person's preferences and workflow. Contributions (issues, pull requests) are not accepted. You're welcome to fork it and make it your own.

## Built with Claude Code

This repo is maintained with the help of [Claude Code](https://claude.com/claude-code).
