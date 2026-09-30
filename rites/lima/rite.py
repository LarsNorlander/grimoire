# profile: work
"""Lima: the headless Linux VM runner, and the rootful Docker VM it hosts.

Docker Desktop is not used on the work profile. The `docker` instance runs
upstream's rootful Docker template; rites/docker wires the host CLI to it.
"""

import subprocess
from pathlib import Path

from arcana.tome import RiteContext

LIMACTL = Path("/opt/homebrew/bin/limactl")
TEMPLATE = "~/.lima-templates/docker.yaml"
INSTANCE = "docker"

# Present once `softwareupdate --install-rosetta` has run.
ROSETTA = Path("/Library/Apple/usr/share/rosetta/rosetta")


def rosetta_ready() -> bool:
    return ROSETTA.exists()


def install_rosetta():
    subprocess.run(
        ["softwareupdate", "--install-rosetta", "--agree-to-license"], check=True
    )


def instance_ready() -> bool:
    if not LIMACTL.exists():
        return True  # runes not inscribed yet: nothing to create against
    result = subprocess.run(
        [LIMACTL, "list", "--quiet"], capture_output=True, text=True, check=True
    )
    return INSTANCE in result.stdout.split()


# Lima merges a template's mounts with its base's by location, so the base's
# read-only home mount would ride along with the template's Workbench mount.
# `--set` runs after that merge and can delete it.
DROP_HOME_MOUNT = 'del(.mounts[] | select(.location == "~"))'


def create_instance():
    # First run downloads the Ubuntu image and provisions Docker: minutes,
    # not seconds. The instance is left running.
    subprocess.run(
        [
            LIMACTL,
            "start",
            "--name",
            INSTANCE,
            "--tty=false",  # don't prompt to confirm the config
            "--set",
            DROP_HOME_MOUNT,
            Path(TEMPLATE).expanduser(),
        ],
        check=True,
    )


def rite(ctx: RiteContext) -> None:
    ctx.copy("docker.yaml")
    ctx.link("docker.yaml", TEMPLATE)
    ctx.hook("install rosetta", install_rosetta, unless=rosetta_ready)
    # The template symlink must exist before this runs; ops execute in order.
    ctx.hook("create lima docker instance", create_instance, unless=instance_ready)
