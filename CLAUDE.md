# Grimoire

Personal machine configuration and scripts, portable across work and personal Macs.

## Scope

**macOS-only, by design.** Linux support is explicitly out of scope.

Grimoire's architecture is shaped by macOS-specific bets that make it coherent:

- `nix-darwin` for system config (system-wide install, launchd, `system.defaults`, `fonts.packages`)
- Homebrew as a first-class escape hatch for packages nixpkgs-darwin doesn't support (e.g., `julia` — `meta.platforms` explicitly excludes darwin) and for GUI casks
- `darwin-rebuild switch` as the activation model
- Profile overlays that assume macOS desktop conventions (AeroSpace, etc.)
- The bash wrapper sources `/run/current-system/sw/bin` and `nix-daemon.sh` — paths only meaningful on nix-darwin

Making grimoire cross-platform would require hedging each of those choices, trading coherence for reach. If a non-macOS machine ever needs configuration management, build a separate tool with its own architectural bets — don't expand grimoire. Do not add realm/OS/platform gating to rites or runes.

## Architecture

Three layers with strict responsibilities:

- **`arcana/`** — Python library and CLI entry point. Provides `RiteContext` which is mode-aware: the same rite script works in build mode and accept mode because the context changes behavior, not the script.
- **`rites/*/rite`** — each rite is a self-contained executable that manages its tool's files using `RiteContext` operations. A single rite can mix `copy()` (source files in the rite dir) and `write()` (generated content) — the distinction is per-file, not per-rite. Arbitrary Python logic (merging, templating) can happen between calls. New modes are handled by `RiteContext`, not by changing rite scripts.
- **`grimoire`** — orchestrator only. Handles prerequisites, profile, and dispatches to rite scripts with the right flags. If `grimoire` needs a separate script to do something, the responsibility is probably in the wrong place — it should be in the rite or in arcana.

The `grimoire` bash wrapper has one job: make sure Python can run. It sources Nix, installs Nix via the Determinate Systems installer if missing, creates the `~/.grimoire` symlink, and ensures `uv` is available (falling back to `nix shell` on first run).

The bash wrapper does **not** prompt for profile or run `darwin-rebuild`; both belong to Python. Keeping bash minimal means the verb semantics live in one place. For the exact implementation, read `grimoire` — it's short.

The Python CLI exposes verbs for applying rites (`cast`), applying runes (`inscribe`), salvaging external changes into rite sources (`accept`), inspecting state (`diff`), managing the profile (`profile`), summoning an ephemeral familiar (`summon`), and a compound `bootstrap` that runs runes + rites for fresh machines. Rites and runes are independent — `bootstrap` is syntactic sugar for `inscribe && cast`. For per-verb usage and flags, see `grimoire --help` and `grimoire <verb> --help`.

Profile is the source of truth in `~/.grimoire-profile` (plain text, single line). The `profile` group is ergonomic UI on top — power users can edit the file directly. Verbs that need the profile read it via `_resolve_profile()`, which prompts interactively if the file is missing.

## Directory Layout

- `arcana/` — Python library and CLI entry point.
- `runes/` — nix-darwin system configuration. A flake with one output per profile, a shared base, and per-profile overlays.
- `rites/<tool>/` — source files and a `rite` script per tool. Each rite imports `RiteContext` and registers declarative ops (`copy`, `write`, `link`, `hook`); the CLI loads the rite module and executes the ops against `tome/`. Rites can also be invoked standalone for debugging: `./rites/<tool>/rite <profile> <grimoire_root> [--force] [--accept]`.
- `cantrips/<tool>/` — standalone utility scripts, organized by the tool they relate to. Always present at `~/.grimoire/cantrips/` (via the `~/.grimoire` symlink). On `PATH` after the zsh rite applies — so `grimoire cast` + a new shell makes them directly invocable.
- `familiars/<name>.nix` — ephemeral toolkits. Each file is a `mkShell` expression; `grimoire summon <name>` dispatches to `nix develop -f familiars/<name>.nix`. Use for tools that should not persist on the machine — language experiments, rarely-used tools, situational toolkits.
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
5. If the rite introduces a user-visible concept or changes the cast/accept/drift model, update `README.md`. Adding another rite to an existing pattern does not require a README change — `rites/` is the source of truth for what's managed.

**Accept mode note:** `grimoire accept` only round-trips `copy()`-managed files (copies the tome file back into the rite source dir). For `write()`-managed files, accept warns and skips — you must manually reconcile generated content.

## Adding a New Familiar

Familiars are for ephemeral tool sets — a language you're learning, a tool you reach for rarely. Create `familiars/<name>.nix` as a `mkShell` expression:

```nix
let pkgs = import <nixpkgs> { };
in pkgs.mkShell {
  buildInputs = with pkgs; [ <packages> ];

  shellHook = ''
    export GRIMOIRE_FAMILIAR=<name>
    # any env vars the tools need
  '';
}
```

`grimoire summon <name>` discovers it automatically — no registration. The starship `custom.familiar` module reads `$GRIMOIRE_FAMILIAR` and shows `<name> familiar` in the prompt; setting that env var is the only convention required.

Decide between rite and familiar by asking *"if the familiar isn't summoned, do I still want this on the machine?"* — if yes, rite or rune; if no, familiar. Tools whose config files are written into `~/.config/...` generally need a rite; tools that accept env-var config paths can bundle their config inside the familiar via `${./config-dir}` path interpolation (nix copies the dir into the store; env var points at the store path).

## README Consistency

`README.md` is user-facing and should stay coherent with the tool's behavior. After any change that alters user-visible behavior (new verbs, changed verb semantics, new/removed concepts, changes to the drift/cast/accept model), re-read `README.md` and update anything that now contradicts reality. Don't re-introduce fragile content: no enumerated file trees, no duplicated `--help` output, no per-package listings in `runes/` descriptions. Point users at `grimoire <verb> --help` or the source directories instead.

## Commit Safety

Before committing, always check that no secrets, credentials, tokens, API keys, or other sensitive data are included in the staged changes. This repo should never contain secrets — they belong in 1Password.

## Conventions

- Python version and external dependencies are declared in `pyproject.toml` (authoritative — don't duplicate the version here)
- Profiles are machine identities; each profile selects a flake output for runes and may drive overlay selection in rites
- Config merging: base files are the complete personal config; overlay files add to it. Arrays concatenate, dicts merge recursively.
- Scripts follow the shebang convention — no file extensions, `chmod +x`
- All symlinks point to `tome/` (gitignored), never to source files — protects tracked files from tools that auto-modify their config

## Key Files

| File | Purpose |
|---|---|
| `grimoire` | Bash wrapper: ensures Nix and uv are available, delegates to the Python CLI |
| `arcana/cli.py` | Python CLI entry point; defines every verb |
| `arcana/tome.py` | `RiteContext` — the API every rite uses |
| `runes/flake.nix` | Nix flake entrypoint (one output per profile) |
| `runes/configuration.nix` | Shared nix-darwin base, applied to every profile |
| `runes/<profile>.nix` | Per-profile overlay (profile-specific packages and config) |
| `pyproject.toml` | uv project config; declares Python version and dependencies |
