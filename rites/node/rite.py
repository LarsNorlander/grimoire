import subprocess
from pathlib import Path

from arcana.tome import RiteContext

# node is managed by nvm (installed via Homebrew in the shared base rune,
# sourced in rites/zsh/zshrc). nvm is a shell function rather than a binary,
# so bootstrapping a node version has to run inside a bash that sources
# nvm.sh. The guard skips when nvm isn't installed yet (runes not inscribed
# on a fresh box) or a default node already exists, so this installs LTS
# exactly once.
NVM_SH = "/opt/homebrew/opt/nvm/nvm.sh"


def _nvm(command, **kwargs):
    return subprocess.run(
        ["bash", "-c", f'export NVM_DIR="$HOME/.nvm"; . "{NVM_SH}"; {command}'],
        **kwargs,
    )


def node_ready() -> bool:
    if not Path(NVM_SH).exists():
        return True  # nothing to do until nvm exists
    return _nvm("nvm which default", capture_output=True).returncode == 0


def install_node():
    _nvm('nvm install --lts && nvm alias default "lts/*"', check=True)


def rite(ctx: RiteContext) -> None:
    ctx.hook("install node (lts) via nvm", install_node, unless=node_ready)
