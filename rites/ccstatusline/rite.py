# profile: work
import subprocess
from pathlib import Path

from arcana.tome import RiteContext

# ccstatusline is npm-only (absent from nixpkgs/homebrew). node is managed by
# nvm (see rites/node), whose npm installs globals into the active version's
# own bin dir — already on PATH — so a plain `npm install -g` is enough.
# nvm is a shell function, so both the guard and the install run inside a
# bash that sources nvm.sh.
#
# On a fresh machine rites cast alphabetically, so this runs before rites/node
# has bootstrapped a default. The guard reports "nothing to do" then; the next
# cast installs it.
NVM_SH = "/opt/homebrew/opt/nvm/nvm.sh"


def _nvm(command, **kwargs):
    return subprocess.run(
        ["bash", "-c", f'export NVM_DIR="$HOME/.nvm"; . "{NVM_SH}"; {command}'],
        **kwargs,
    )


def ccstatusline_ready() -> bool:
    if not Path(NVM_SH).exists():
        return True  # nvm not installed yet: nothing to do
    default = _nvm("nvm which default", capture_output=True, text=True)
    if default.returncode != 0:
        return True  # no default node yet: rites/node installs it
    node_bin = Path(default.stdout.strip()).parent
    return (node_bin / "ccstatusline").exists()


def install_ccstatusline():
    _nvm("nvm use --silent default && npm install -g ccstatusline", check=True)


def rite(ctx: RiteContext) -> None:
    ctx.hook("install ccstatusline", install_ccstatusline, unless=ccstatusline_ready)
    ctx.copy("settings.json")
    ctx.link("settings.json", "~/.config/ccstatusline/settings.json")
    # Claude Code's settings.json differs per machine (see rites/claude); own
    # only the statusLine entry that wires ccstatusline in.
    ctx.patch("claude-settings.json", "~/.claude/settings.json")
