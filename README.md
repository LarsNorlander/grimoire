# Grimoire

Personal config and scripts, portable across machines.

## Install

Clone directly to `~/.grimoire` and run `cast`:

```
git clone git@github.com:LarsNorlander/grimoire.git ~/.grimoire
~/.grimoire/cast
```

If cloned elsewhere (e.g. inside a workspace), `cast` creates a `~/.grimoire` symlink pointing to the repo.

## Structure

```
grimoire/
├── cast              # deployment script
├── config/           # configuration files
│   └── aerospace.toml
└── scripts/          # executable scripts
    └── resize-window-pct
```

Configs reference scripts via `$HOME/.grimoire/scripts/` so paths work regardless of where the repo is cloned.
