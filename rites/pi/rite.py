# profile: personal
from arcana.tome import RiteContext


def rite(ctx: RiteContext) -> None:
    ctx.copy("AGENTS.md", "settings.json")
    ctx.link("AGENTS.md", "~/.pi/agent/AGENTS.md")
    ctx.link("settings.json", "~/.pi/agent/settings.json")
