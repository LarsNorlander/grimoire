# Grimoire

Personal Mac configuration — what's installed and how tools are configured, portable across work and personal machines. (The fantasy naming is intentional: "rites" are config scripts, "runes" are Nix packages, "tome" is the build output; `grimoire cast` applies rites and `grimoire inscribe` applies runes.)

## Install

On a new machine, clone directly to `~/.grimoire` and invoke the bash wrapper by full path (it's not on `PATH` yet):

```
git clone git@github.com:LarsNorlander/grimoire.git ~/.grimoire
~/.grimoire/grimoire bootstrap
```

`bootstrap` is the end-to-end provisioning verb. The bash wrapper ensures Nix is installed and that `uv` is available (via `nix shell nixpkgs#uv` on truly first run), creates the `~/.grimoire` symlink if needed, then hands off to Python. The `bootstrap` verb itself prompts for profile (work/personal), applies runes (`darwin-rebuild switch` — Nix packages, Homebrew casks, fonts, macOS defaults), then applies all rites. After the zsh rite runs, `~/.grimoire` is on `PATH`, so from the next shell onward you can use `grimoire` directly.

`bootstrap` is idempotent — safe to re-run. After the initial bootstrap, use the narrower verbs (`cast`, `inscribe`, `accept`, `diff`) for day-to-day work.

### `grimoire cast` — apply rites

Rites are the common case: every time you tweak a tool config, `cast` rebuilds the tome and refreshes symlinks.

- `grimoire cast` — apply all rites
- `grimoire cast <tool> [<tool> ...]` — apply only the named rites
- `grimoire cast --dry-run` — preview what would be built/linked without making changes
- `grimoire cast --force` / `grimoire accept <tool>` — see [Drift detection](#drift-detection) below

### `grimoire inscribe` — apply runes

Runes are the system layer: packages, Homebrew casks, fonts, macOS defaults. Run `inscribe` after editing `runes/*.nix`.

- `grimoire inscribe` — run `darwin-rebuild switch` against the profile's flake output
- `grimoire inscribe --dry-run` — run `darwin-rebuild build` (materializes the derivation without activating)

### `grimoire profile` — show or change the machine profile

The profile (`work` or `personal`) is stored in `~/.grimoire-profile` and selects which flake output runes target and which overlay rites apply.

- `grimoire profile` — print the current profile (exits 1 if unset)
- `grimoire profile set work` / `set personal` — set explicitly
- `grimoire profile unset` — clear the profile (next verb that needs one will prompt)

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
│   ├── ccstatusline/
│   ├── claude/             # Claude Code settings + global CLAUDE.md
│   ├── gh-dash/            # work profile only
│   ├── ghostty/
│   ├── git/
│   ├── starship/
│   ├── zed/
│   └── zsh/                # copy + profile overlay + generated completion
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
- **`grimoire`** — the orchestrator. A thin bash wrapper (ensures Nix is installed, manages the `~/.grimoire` symlink, makes `uv` available via `nix shell` on first run) that hands off to a Python CLI (`arcana/cli.py`) for profile selection, rune application, prerequisite sync, and rite dispatch. It doesn't know what any tool's config looks like.

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
- `grimoire accept <tool> [<tool2> ...]` — pull the external changes back into the rite's source directory (only works for `copy()`-managed files; `write()` files need manual reconciliation since they're generated)

### Inspecting drift

`grimoire diff [<tool>]` shows how the current tome state compares along three axes — by default all three are shown in summary form:

- **drift** — tome vs. manifest (what's changed on disk since last cast)
- **cast** — tome vs. what a fresh rebuild would produce (what `grimoire cast` would change)
- **accept** — tome vs. rite source (what `grimoire accept` would pull back; `copy()`-managed files only)

When the same file has both drift and pending cast changes, `diff` flags it as a potential conflict — both `cast --force` and `accept` would each clobber something.

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
