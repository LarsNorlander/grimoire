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
├── config/                 # config sources (per tool)
│   └── aerospace/
│       ├── build           # builds aerospace.toml from fragments
│       ├── base.toml       # shared config (all machines)
│       └── work.toml       # work-only overlay
├── scripts/                # standalone scripts
│   └── resize-window-pct
└── tome/                   # built configs (gitignored)
```

## How Config Building Works

Each tool under `config/` has its own `build` script. `cast` runs them all with the active profile (`work` or `personal`).

For aerospace: `base.toml` is the complete personal config. On work machines, `work.toml` is merged in — adding workspaces (Dia, Slack, Notion), keybindings, and monitor assignments. The built result lands in `tome/aerospace.toml` and is symlinked to `~/.aerospace.toml`.

Configs reference scripts via `$HOME/.grimoire/scripts/` so paths work regardless of where the repo is cloned.
