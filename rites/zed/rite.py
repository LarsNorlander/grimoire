from arcana.tome import RiteContext


def rite(ctx: RiteContext) -> None:
    ctx.copy("settings.json")
    ctx.link("settings.json", "~/.config/zed/settings.json")
