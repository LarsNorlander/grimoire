# profile: work
"""Docker CLI on the host, pointed at the Lima VM's daemon (see rites/lima).

Rites cast alphabetically, so this runs before rites/lima has created the
instance. That is fine: a docker context is metadata under ~/.docker and
needs no live socket; it starts working once the VM is up.
"""

import subprocess
from pathlib import Path

from arcana.tome import RiteContext

DOCKER = Path("/opt/homebrew/bin/docker")
CONTEXT = "lima-docker"
# What `limactl list docker --format '{{.Dir}}/sock/docker.sock'` prints.
SOCKET = Path.home() / ".lima" / "docker" / "sock" / "docker.sock"


def context_ready() -> bool:
    if not DOCKER.exists():
        return True  # runes not inscribed yet: nothing to create with
    result = subprocess.run(
        [DOCKER, "context", "inspect", CONTEXT], capture_output=True, text=True
    )
    return result.returncode == 0


def create_context():
    subprocess.run(
        [DOCKER, "context", "create", CONTEXT, "--docker", f"host=unix://{SOCKET}"],
        check=True,
    )


def rite(ctx: RiteContext) -> None:
    # Prefer a context over exporting DOCKER_HOST: the context persists, and
    # an exported DOCKER_HOST overrides it and confuses tools that read one
    # but not the other.
    ctx.hook("create docker context", create_context, unless=context_ready)
    # The CLI rewrites config.json itself (auths, and currentContext on
    # `docker context use`); own only the keys that wire it to Lima and to
    # Homebrew's plugin dir, which the CLI doesn't search by default.
    ctx.patch("config.json", "~/.docker/config.json")
