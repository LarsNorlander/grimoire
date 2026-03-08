# Grimoire

Personal Mac configuration — what's installed and how tools are configured, portable across work and personal machines.

## Install

Clone directly to `~/.grimoire` and run `cast`:

```
git clone git@github.com:LarsNorlander/grimoire.git ~/.grimoire
~/.grimoire/cast
```

`cast` will:
1. Verify/install Nix (Determinate) if missing
2. Ask whether this is a work or personal machine (stored in `~/.grimoire-profile`)
3. Ensure `~/.grimoire` symlink exists
4. Apply nix-darwin config (`darwin-rebuild switch`) — installs packages, Homebrew apps, macOS defaults
5. Sync Python venv (`uv sync`)
6. Build rite configs into `tome/` and symlink into place

If cloned elsewhere (e.g. inside a workspace), `cast` creates a `~/.grimoire` symlink pointing to the repo.

Re-run `cast` any time to rebuild configs. Use `cast --recast` to change the machine profile. Use `cast --force` to overwrite externally modified tome files, or `cast --accept <tool>` to pull changes back into rite sources.

## Structure

```
grimoire/
├── cast                    # deployment orchestrator (bash)
├── pyproject.toml          # Python dependencies (managed by uv)
├── arcana/                 # shared build library (RiteContext)
├── runes/                  # nix-darwin system config
│   ├── flake.nix           # flake entrypoint (personal + work outputs)
│   ├── configuration.nix   # shared base (packages, Homebrew, macOS defaults)
│   ├── personal.nix        # personal profile overlay
│   └── work.nix            # work profile overlay
├── rites/                  # dotfile sources (per tool)
│   ├── aerospace/          # merges base + work overlay
│   ├── git/
│   ├── ghostty/
│   ├── starship/
│   ├── zed/
│   ├── ccstatusline/
│   └── gh-dash/
├── cantrips/               # standalone utility scripts
│   └── resize-window-pct
└── tome/                   # built configs (gitignored)
```

## What Gets Managed

**System layer (`runes/` — nix-darwin):**
- CLI tools via Nix: `uv`, `bat`, `btop`, `fastfetch`, `neovim`, `nodejs`, `starship`
- GUI apps via Homebrew casks: AeroSpace, Ghostty, 1Password CLI, Scroll Reverser
- Homebrew formulae: julia
- macOS system defaults: dark mode, dock position, minimize effect

**Config layer (`rites/` — grimoire rites):**

| Tool | What's configured |
|---|---|
| AeroSpace | Workspaces, keybindings (work adds extra workspaces) |
| Git | User config, aliases |
| Ghostty | Font, colors, keybindings |
| Starship | Prompt modules |
| Zed | Editor settings |
| CCStatusline | Status bar settings |
| gh-dash | GitHub dashboard config |

## How It Works

Each tool under `rites/` has a `rite` script. `cast` runs them all with the active profile (`work` or `personal`). Built configs land in `tome/` (gitignored) and are symlinked to where each tool expects them.

For simple configs, the rite copies the file. For tools like AeroSpace, the rite merges a base config with a profile-specific overlay.

Symlinks always point to `tome/`, so tools that auto-modify their config write to the gitignored copy — tracked source files stay clean. A manifest tracks content hashes; if a file is externally modified, `cast` warns before overwriting.

Profile (`work`/`personal`) is applied at both layers: nix-darwin loads the right flake output, rites load profile-specific overlays.
