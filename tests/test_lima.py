"""The lima rite's hook guards, with limactl and softwareupdate stubbed out.

Run with: uv run python -m unittest
"""

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
RITE_DIR = REPO / "rites" / "lima"


def _load():
    spec = importlib.util.spec_from_file_location("lima_rite", RITE_DIR / "rite.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstanceGuard(unittest.TestCase):
    def setUp(self):
        self.lima = _load()

    def test_nothing_to_do_until_limactl_is_installed(self):
        with (
            mock.patch.object(self.lima, "LIMACTL", Path("/nonexistent/limactl")),
            mock.patch.object(subprocess, "run") as run,
        ):
            self.assertTrue(self.lima.instance_ready())
            run.assert_not_called()

    def test_done_when_limactl_lists_the_instance(self):
        listing = subprocess.CompletedProcess([], 0, stdout="ubuntu\ndocker\n")
        with (
            mock.patch.object(self.lima, "LIMACTL", Path("/")),
            mock.patch.object(subprocess, "run", return_value=listing),
        ):
            self.assertTrue(self.lima.instance_ready())

    def test_pending_when_only_other_instances_exist(self):
        listing = subprocess.CompletedProcess([], 0, stdout="ubuntu\n")
        with (
            mock.patch.object(self.lima, "LIMACTL", Path("/")),
            mock.patch.object(subprocess, "run", return_value=listing),
        ):
            self.assertFalse(self.lima.instance_ready())

    def test_create_starts_from_the_managed_template_without_a_tty(self):
        with mock.patch.object(subprocess, "run") as run:
            self.lima.create_instance()
        argv = [str(a) for a in run.call_args.args[0]]
        self.assertEqual(argv[1:4], ["start", "--name", "docker"])
        self.assertIn("--tty=false", argv)
        self.assertEqual(argv[-1], str(Path(self.lima.TEMPLATE).expanduser()))

    def test_create_drops_the_base_templates_home_mount(self):
        with mock.patch.object(subprocess, "run") as run:
            self.lima.create_instance()
        argv = [str(a) for a in run.call_args.args[0]]
        self.assertEqual(argv[argv.index("--set") + 1], self.lima.DROP_HOME_MOUNT)
        self.assertIn('.location == "~"', self.lima.DROP_HOME_MOUNT)


class RosettaGuard(unittest.TestCase):
    def test_follows_the_rosetta_runtime_marker(self):
        lima = _load()
        with mock.patch.object(lima, "ROSETTA", Path("/")):
            self.assertTrue(lima.rosetta_ready())
        with mock.patch.object(lima, "ROSETTA", Path("/nonexistent")):
            self.assertFalse(lima.rosetta_ready())
