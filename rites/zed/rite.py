"""Build shared Zed settings with an optional profile overlay."""

import json

from arcana.patch import load, merge
from arcana.tome import RiteContext


def build_settings(*, profile, rite_dir, **_):
    settings = load(rite_dir / "settings.json")
    overlay = rite_dir / f"{profile}.json"
    if overlay.exists():
        settings = merge(settings, load(overlay))
    return json.dumps(settings, indent=2, ensure_ascii=False) + "\n"


def rite(ctx: RiteContext) -> None:
    ctx.write("settings.json", build_settings)
    ctx.link("settings.json", "~/.config/zed/settings.json")
