# Grimoire

Personal Mac configuration — what's installed and how tools are configured, portable across work and personal machines. (The fantasy naming is intentional: "rites" are config scripts, "runes" are Nix packages, "tome" is the build output, and `grimoire cast` ties it all together.)

## Install

Clone directly to `~/.grimoire` and run `grimoire cast`:

```
git clone git@github.com:LarsNorlander/grimoire.git ~/.grimoire
~/.grimoire/grimoire cast
```

`grimoire cast` will:
1. Verify/install Nix (Determinate) if missing
2. Link `~/.grimoire` to the repo (if cloned elsewhere)
3. Ask whether this is a work or personal machine (stored in `~/.grimoire-profile`)
4. Apply nix-darwin config (`darwin-rebuild switch`) — installs packages, Homebrew apps, macOS defaults
5. Sync Python venv (`uv sync`)
6. Build rite configs into `tome/` and symlink into place

Re-run `grimoire cast` any time to rebuild configs.

- `grimoire cast --recast` — change the machine profile
- `grimoire cast --dry-run` — preview what would be built/linked without making changes
- `grimoire cast --only rites|runes` — run only rites or runes (skip the other)
- `grimoire cast --force` / `--accept <tool>` — see [Drift detection](#drift-detection) below

## Structure

```
grimoire/
├── grimoire                # Bash bootstrap: sources nix, delegates to Python CLI
├── pyproject.toml          # Python dependencies (managed by uv)
├── arcana/                 # Python library (RiteContext) + CLI entry point (cli.py)
├── runes/                  # nix-darwin system config
│   ├── flake.nix           # flake entrypoint (personal + work outputs)
│   ├── configuration.nix   # shared base (packages, Homebrew, macOS defaults)
│   ├── personal.nix        # personal profile overlay
│   └── work.nix            # work profile overlay
├── rites/                  # dotfile sources (per tool)
│   ├── aerospace/          # merges base + profile overlay
│   ├── git/
│   ├── ghostty/
│   ├── starship/
│   ├── zed/
│   ├── ccstatusline/
│   ├── gh-dash/
│   └── zsh/
├── cantrips/               # standalone utility scripts
│   ├── aerospace/
│   │   └── resize-window-pct
│   └── claude/
│       └── block-destructive-git
└── tome/                   # built configs (gitignored)
```

## How It Works

Grimoire has three layers, each with a single job:

- **`arcana/`** — a Python library and CLI entry point. Provides `RiteContext`, which is the only API rite scripts need. The context is *mode-aware*: the same rite script works in build mode and accept mode because the context changes behavior, not the script. Rites never branch on mode.
- **`rites/*/rite`** — one self-contained executable per tool. Each rite describes *what* to build and where to link it, using two operations: `copy()` for static files and `write()` for generated content. A single rite can mix both — the distinction is per-file, not per-rite.
- **`grimoire`** — the orchestrator. A thin bash bootstrap (Nix, symlink, first-run runes) that hands off to a Python CLI (`arcana/cli.py`) for profile selection, rune application, prerequisite sync, and rite dispatch. It doesn't know what any tool's config looks like.

### `copy()` vs `write()`

**`copy()`** is for files you edit directly. The Starship rite is the simplest example — it's the entire script:

```python
ctx = RiteContext.from_args()
ctx.copy("starship.toml")
ctx.link("starship.toml", "~/.config/starship.toml")
```

**`write()`** takes a builder function for configs that need merging, templating, or any other transformation. The AeroSpace rite uses this to merge a base config with a profile-specific overlay via tomlkit:

```python
def build_aerospace(*, profile, rite_dir, **_):
    with open(rite_dir / "base.toml") as f:
        doc = tomlkit.load(f)
    overlay_file = {"work": "work.toml", "personal": "personal.toml"}.get(profile)
    if overlay_file:
        with open(rite_dir / overlay_file) as f:
            overlay = tomlkit.load(f)
        merge_into_table(doc, overlay)
    return tomlkit.dumps(doc)

ctx = RiteContext.from_args()
ctx.write("aerospace.toml", build_aerospace)
ctx.link("aerospace.toml", "~/.aerospace.toml")
```

The builder receives `profile`, `rite_dir`, and `grimoire_root` as kwargs — enough to load files and make profile-aware decisions.

### Drift detection

Symlinks always point to `tome/` (gitignored), so tools that auto-modify their config write to the build copy — tracked source files stay clean.

A manifest (`tome/.manifest`) tracks content hashes of every built file. If a tome file is externally modified, `grimoire cast` warns and skips it instead of silently overwriting your changes. From there:

- `grimoire cast --force` — overwrite and rebuild from source
- `grimoire cast --accept <tool> [--accept <tool2> ...]` — pull the external changes back into the rite's source directory (only works for `copy()`-managed files; `write()` files need manual reconciliation since they're generated)

### Inspecting drift

`grimoire diff [<tool>]` shows how the current tome state compares along three axes — by default all three are shown in summary form:

- **drift** — tome vs. manifest (what's changed on disk since last cast)
- **cast** — tome vs. what a fresh rebuild would produce (what `grimoire cast` would change)
- **accept** — tome vs. rite source (what `--accept` would pull back; `copy()`-managed files only)

When the same file has both drift and pending cast changes, `diff` flags it as a potential conflict — both `cast --force` and `--accept` would each clobber something.

Flags:

- `--drift` / `--cast` / `--accept` — restrict to one or more axes (combinable)
- `--build` — evaluate `--cast` for `write()` rites (re-runs their generators; otherwise shown as `?`)
- `--full` — print unified diffs instead of summary status

Exit codes: `0` no changes, `1` changes present, `2` error.

## Adding a New Config

Create `rites/<tool>/` with your source files and a `rite` script (`chmod +x`). Use `copy()` for static files or `write()` with a builder for generated ones (see [How It Works](#how-it-works) above). `grimoire cast` discovers the new rite automatically on the next run.

## Secrets

Secrets are managed through [1Password](https://1password.com/) and its CLI (`op`). Nothing sensitive is stored in this repo — credentials, tokens, and keys are referenced from 1Password at runtime.

## Contributing

This is a personal configuration repo — it reflects one person's preferences and workflow. Contributions (issues, pull requests) are not accepted. You're welcome to fork it and make it your own.

## Built with Claude Code

This repo is maintained with the help of [Claude Code](https://claude.com/claude-code).
