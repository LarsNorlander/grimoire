# profile: work

from arcana.tome import RiteContext


def rite(ctx: RiteContext) -> None:
    ctx.copy("config.yml")
    ctx.link("config.yml", "~/.config/gh-dash/config.yml")
