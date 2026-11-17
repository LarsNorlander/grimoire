# profile: work
"""Herdr Desktop customizations: our own mods, and the `mdv` command.

Herdr resolves a mod's modules by real path and refuses any that lead
outside the mod folder, so mods are install()ed as real files rather than
linked into tome. Herdr writes its own files into ~/.config/herdr-app
(the guide, type files, shipped mods, state); none of those are managed
here.
"""

from arcana.tome import RiteContext

# Herdr writes these into every mod folder, and `herdr-app check` writes them
# into whatever folder it checks. They are Herdr's, never ours to install.
HERDR_WRITES = ("*.d.ts", "jsconfig.json")


def rite(ctx: RiteContext) -> None:
    ctx.install("mods/md", "~/.config/herdr-app/mods/md", exclude=HERDR_WRITES)
    ctx.copy("mdv")
    ctx.link("mdv", "~/.local/bin/mdv")
