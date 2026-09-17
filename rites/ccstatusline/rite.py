# profile: work
import subprocess
from pathlib import Path

from arcana.tome import RiteContext

# ccstatusline is npm-only (absent from nixpkgs/homebrew). The bare
# `ccstatusline` command in Claude's settings.json is the documented
# "pinned global install" path; install it here if missing, mirroring
# how the zsh rite bootstraps oh-my-zsh. ~/.npm-global/bin is on PATH
# (see rites/zsh/zshrc), and npm's own prefix is the read-only nix store,
# so target the writable prefix explicitly.
PREFIX = Path.home() / ".npm-global"


def install_ccstatusline():
    subprocess.run(
        ["npm", "install", "-g", "--prefix", str(PREFIX), "ccstatusline"],
        check=True,
    )


def rite(ctx: RiteContext) -> None:
    ctx.hook("install ccstatusline", install_ccstatusline,
             unless=(PREFIX / "bin" / "ccstatusline").exists)
    ctx.copy("settings.json")
    ctx.link("settings.json", "~/.config/ccstatusline/settings.json")
