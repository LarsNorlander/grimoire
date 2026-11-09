# profile: work
from arcana.tome import RiteContext


def rite(ctx: RiteContext) -> None:
    ctx.copy("CLAUDE.md", "herdr-workflow.md", "herdr-layout.md")
    ctx.link("CLAUDE.md", "~/.claude/CLAUDE.md")
    ctx.link("herdr-workflow.md", "~/.claude/skills/herdr-workflow/SKILL.md")
    ctx.link("herdr-layout.md", "~/.claude/skills/herdr-layout/SKILL.md")
