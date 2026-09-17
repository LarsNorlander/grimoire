import os
import subprocess
from pathlib import Path

from arcana.tome import RiteContext


def build_grimoire_completion(*, grimoire_root, **_):
    result = subprocess.run(
        ["uv", "run", "python", "-m", "arcana.cli"],
        env={**os.environ, "_GRIMOIRE_COMPLETE": "zsh_source"},
        capture_output=True,
        text=True,
        cwd=grimoire_root,
    )
    result.check_returncode()
    return result.stdout


OMZ_DIR = Path.home() / ".oh-my-zsh"


def install_omz():
    subprocess.run(
        [
            "sh",
            "-c",
            (
                "curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh"
                " | sh -s - --unattended --keep-zshrc"
            ),
        ],
        check=True,
    )


def rite(ctx: RiteContext) -> None:
    ctx.hook("install oh-my-zsh", install_omz, unless=OMZ_DIR.exists)
    ctx.copy("zshrc")
    ctx.link("zshrc", "~/.zshrc")
    ctx.copy(f"{ctx.profile}.zsh")
    ctx.link(f"{ctx.profile}.zsh", "~/.config/zsh/profile.zsh")
    ctx.write("grimoire_completion", build_grimoire_completion)
    ctx.link("grimoire_completion", "~/.config/zsh/completions/_grimoire")
