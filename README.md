# Grimoire

Personal macOS configuration: system packages, GUI apps, shell setup, and tool configs for work and personal Macs.

Grimoire is intentionally macOS-only. It is built around nix-darwin, Homebrew, `darwin-rebuild switch`, and macOS desktop conventions; Linux support belongs in a separate tool, not behind conditionals here.

## Install

On a new machine, clone to `~/.grimoire` and run the wrapper directly:

```sh
git clone git@github.com:LarsNorlander/grimoire.git ~/.grimoire
~/.grimoire/grimoire bootstrap
```

`bootstrap` prompts for a profile, applies runes, then applies rites. It is safe to re-run.

After bootstrap, use the narrower verbs for day-to-day work. Run `grimoire --help` and `grimoire <verb> --help` for the current flag reference.

## Concepts

- **Runes** (`runes/`) are nix-darwin system configuration: packages, Homebrew apps, fonts, and macOS defaults.
- **Rites** (`rites/<tool>/`) build and link per-tool config into place.
- **Tome** (`tome/`) is gitignored build output. Managed symlinks point here, not directly at tracked source files.
- **Familiars** (`familiars/`) are ephemeral Nix shells for tools that should not persist on the machine.
- **Profiles** (`work` or `personal`) select the nix-darwin output and any profile-specific rite behavior. The current profile lives in `~/.grimoire-profile`.

## Commands

- `grimoire bootstrap` — provision a fresh machine by applying runes, then rites.
- `grimoire inscribe` — apply runes.
- `grimoire cast [tool ...]` — apply rites, rebuilding tome files and refreshing symlinks.
- `grimoire diff [tool]` — inspect drift between rite sources, tome files, and the manifest.
- `grimoire accept <tool ...>` — copy externally edited tome files back to rite sources where possible.
- `grimoire profile` — show or change the current profile.
- `grimoire summon <name>` — enter an ephemeral familiar shell, or run one command in it with `--`.
- `grimoire scribe [tool ...]` — generate cheatsheet JSON from rites that document themselves.

## Rites and drift

A rite is an executable script that registers operations with `RiteContext`:

- `copy()` copies source files from the rite into `tome/`.
- `write()` generates files into `tome/` from Python builders.
- `link()` creates user-facing symlinks to `tome/`.
- `patch()` owns selected keys inside a JSON file the machine otherwise owns. The rite holds a fragment; its leaf keys are merged into the live file in place, so this is the one operation that writes a real file instead of symlinking. Arrays are replaced whole, not merged.
- `hook()` performs necessary imperative setup.
- `doc()` registers cheatsheet data for `grimoire scribe`.

`tome/.manifest` records hashes of built files. If a tool edits a managed file in `tome/`, `cast` skips it rather than overwriting it silently. Use `diff` to inspect the state, `cast --force` to rebuild from source, or `accept` to pull external edits back into `copy()`-managed rite sources. Generated `write()` files require manual reconciliation. For `patch()` files, drift and accept look only at the owned keys; the rest of the file is free to change.

Profile-specific rites use a header directive:

```python
#!/usr/bin/env python3
# profile: work
```

Rites without a directive apply to every profile.

## Cheatsheets

`grimoire scribe` writes schema-validated JSON for documented rites. Grimoire only produces data; rendering belongs to [homepage](https://github.com/LarsNorlander/homepage). By default, sheets are written to homepage's content directory; override with `--output` or `GRIMOIRE_SCRIBE_OUTPUT`.

Generated sheets carry a `generator` marker, and grimoire only overwrites or prunes sheets it owns so hand-written sheets can share the same directory.

## Secrets

Secrets are managed through [1Password](https://1password.com/) and its CLI (`op`). Nothing sensitive belongs in this repository.

## Contributing

This is a personal configuration repo. Contributions are not accepted, but you are welcome to fork it.

## Built with Pi

This repo is maintained with the help of Pi.
