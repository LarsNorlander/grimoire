from arcana.tome import RiteContext


def rite(ctx: RiteContext) -> None:
    ctx.copy("starship.toml")
    ctx.link("starship.toml", "~/.config/starship.toml")
