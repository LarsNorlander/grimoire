from arcana.tome import RiteContext


def rite(ctx: RiteContext) -> None:
    ctx.copy("config")
    ctx.link("config", "~/.config/ghostty/config")
