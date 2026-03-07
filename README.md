# Grimoire

Personal config and scripts, portable across machines.

## Install

Clone directly to `~/.grimoire` and run `cast`:

```
git clone git@github.com:LarsNorlander/grimoire.git ~/.grimoire
~/.grimoire/cast
```

`cast` will:
1. Install prerequisites (Homebrew, uv) if missing
2. Ask whether this is a work or personal machine
3. Build config files from composable sources
4. Symlink everything into place

If cloned elsewhere (e.g. inside a workspace), `cast` creates a `~/.grimoire` symlink pointing to the repo.

Re-run `cast` any time to rebuild configs. Use `cast --recast` to change the machine profile.

## Structure

```
grimoire/
├── cast                    # deployment orchestrator
├── pyproject.toml          # Python dependencies (managed by uv)
├── arcana/                 # shared build library
├── rites/                 # config sources (per tool)
│   ├── aerospace/
│   │   ├── build           # merges base + work overlay
│   │   ├── base.toml       # shared config (all machines)
│   │   └── work.toml       # work-only overlay
│   ├── git/
│   ├── starship/
│   ├── ccstatusline/
│   ├── gh-dash/
│   └── zed/
├── cantrips/                # standalone scripts
│   └── resize-window-pct
└── tome/                   # built configs (gitignored)
```

## How It Works

Each tool under `rites/` has its own `build` script. `cast` runs them all with the active profile (`work` or `personal`). Built configs land in `tome/` (gitignored) and are symlinked to where each tool expects them.

For simple configs, the build script just copies the file. For tools like AeroSpace, the build script merges a base config with profile-specific overlays.

Symlinks always point to `tome/`, so tools that auto-modify their config write to the gitignored copy — tracked source files stay clean.
