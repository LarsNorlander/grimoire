# profile: personal
from arcana.tome import RiteContext


def rite(ctx: RiteContext) -> None:
    ctx.copy("AGENTS.md")
    ctx.link("AGENTS.md", "~/.pi/agent/AGENTS.md")
    # pi rewrites settings.json itself (lastChangelogVersion and friends);
    # own only the preferences.
    ctx.patch("settings.json", "~/.pi/agent/settings.json")
