# profile: work
from arcana.tome import RiteContext


def rite(ctx: RiteContext) -> None:
    ctx.copy("CLAUDE.md")
    ctx.link("CLAUDE.md", "~/.claude/CLAUDE.md")
