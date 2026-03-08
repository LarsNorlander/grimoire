# Grimoire

Personal Mac configuration — what's installed and how tools are configured, portable across work and personal machines. (The fantasy naming is intentional: "rites" are config scripts, "runes" are Nix packages, "tome" is the build output, and `cast` ties it all together.)

## Install

Clone directly to `~/.grimoire` and run `cast`:

```
git clone git@github.com:LarsNorlander/grimoire.git ~/.grimoire
~/.grimoire/cast
```

`cast` will:
1. Verify/install Nix (Determinate) if missing
2. Ask whether this is a work or personal machine (stored in `~/.grimoire-profile`)
3. Apply nix-darwin config (`darwin-rebuild switch`) — installs packages, Homebrew apps, macOS defaults
4. Sync Python venv (`uv sync`)
5. Build rite configs into `tome/` and symlink into place

If cloned elsewhere (e.g. inside a workspace), `cast` creates a `~/.grimoire` symlink pointing to the repo before proceeding.

Re-run `cast` any time to rebuild configs.

- `cast --recast` — change the machine profile
- `cast --force` — overwrite externally modified tome files
- `cast --accept <tool> [--accept <tool2> ...]` — pull external changes back into rite sources

## Structure

```
grimoire/
├── cast                    # Bash bootstrap: sources nix, delegates to Python CLI
├── pyproject.toml          # Python dependencies (managed by uv)
├── arcana/                 # shared build library (RiteContext)
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
│   └── resize-window-pct
└── tome/                   # built configs (gitignored)
```

## What Gets Managed

**System layer (`runes/` — nix-darwin):**
- CLI tools via Nix: `uv`, `bat`, `btop`, `fastfetch`, `go`, `neovim`, `nodejs`, `starship`
- GUI apps via Homebrew casks: AeroSpace, Ghostty, 1Password CLI, Scroll Reverser
- Fonts via Nix: JetBrainsMono Nerd Font
- macOS system defaults: dark mode, dock position, minimize effect
- Personal profile adds: `julia`
- Work profile adds: `awscli2`, `gh`, `golangci-lint`, `jq`, `kubectl`, `mysql-client` (Nix); Typora (Homebrew cask)

**Config layer (`rites/` — grimoire rites):**

| Tool | What's configured |
|---|---|
| AeroSpace | Workspaces, keybindings (work adds extra workspaces) |
| Git | User config, aliases |
| Ghostty | Font, colors, keybindings |
| Starship | Prompt modules |
| Zed | Editor settings |
| Claude Code statusline | Status bar settings |
| gh-dash | GitHub dashboard config (work only) |
| zsh | `~/.zshrc` (PATH, fpath, compinit); generated `_cast` zsh completion |

Profile (`work`/`personal`) applies at both layers: nix-darwin loads the right flake output, and rites load profile-specific overlays.

## How It Works

Grimoire has three layers, each with a single job:

- **`arcana/`** — a pure Python library. Provides `RiteContext`, which is the only API rite scripts need. The context is *mode-aware*: the same rite script works in build mode and accept mode because the context changes behavior, not the script. Rites never branch on mode.
- **`rites/*/rite`** — one self-contained executable per tool. Each rite describes *what* to build and where to link it, using two operations: `copy()` for static files and `write()` for generated content. A single rite can mix both — the distinction is per-file, not per-rite.
- **`cast`** — the orchestrator. A thin bash bootstrap (Nix, symlink, first-run runes) that hands off to a Python CLI (`arcana/cli.py`) for profile selection, rune application, prerequisite sync, and rite dispatch. It doesn't know what any tool's config looks like.

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

A manifest (`tome/.manifest`) tracks content hashes of every built file. If a tome file is externally modified, `cast` warns and skips it instead of silently overwriting your changes. From there:

- `cast --force` — overwrite and rebuild from source
- `cast --accept <tool> [--accept <tool2> ...]` — pull the external changes back into the rite's source directory (only works for `copy()`-managed files; `write()` files need manual reconciliation since they're generated)

## Adding a New Config

Create `rites/<tool>/` with your source files and a `rite` script (`chmod +x`).

**Static file** — copy and link:

```python
#!/usr/bin/env python3
from arcana.tome import RiteContext

ctx = RiteContext.from_args()
ctx.copy("config.toml")
ctx.link("config.toml", "~/.config/tool/config.toml")
```

**Generated file** — use a builder:

```python
#!/usr/bin/env python3
from arcana.tome import RiteContext

def build_config(*, profile, rite_dir, **_):
    # load, merge, template — return content as a string
    return result

ctx = RiteContext.from_args()
ctx.write("config.toml", build_config)
ctx.link("config.toml", "~/.config/tool/config.toml")
```

That's it. `cast` discovers the new rite automatically on the next run.

## Secrets

Secrets are managed through [1Password](https://1password.com/) and its CLI (`op`). Nothing sensitive is stored in this repo — credentials, tokens, and keys are referenced from 1Password at runtime.

## Contributing

This is a personal configuration repo — it reflects one person's preferences and workflow. Contributions (issues, pull requests) are not accepted. You're welcome to fork it and make it your own.

## Built with Claude Code

This repo is maintained with the help of [Claude Code](https://claude.com/claude-code).
