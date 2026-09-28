"""The docker rite's context guard, with the docker CLI stubbed out.

Run with: uv run python -m unittest
"""

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
RITE_DIR = REPO / "rites" / "docker"


def _load():
    spec = importlib.util.spec_from_file_location("docker_rite", RITE_DIR / "rite.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContextGuard(unittest.TestCase):
    def setUp(self):
        self.docker = _load()

    def test_nothing_to_do_until_docker_is_installed(self):
        with (
            mock.patch.object(self.docker, "DOCKER", Path("/nonexistent/docker")),
            mock.patch.object(subprocess, "run") as run,
        ):
            self.assertTrue(self.docker.context_ready())
            run.assert_not_called()

    def test_done_iff_inspect_succeeds(self):
        with mock.patch.object(self.docker, "DOCKER", Path("/")):
            for code, expected in ((0, True), (1, False)):
                with self.subTest(returncode=code):
                    result = subprocess.CompletedProcess([], code)
                    with mock.patch.object(subprocess, "run", return_value=result):
                        self.assertEqual(self.docker.context_ready(), expected)

    def test_create_points_the_context_at_the_lima_socket(self):
        with mock.patch.object(subprocess, "run") as run:
            self.docker.create_context()
        argv = [str(a) for a in run.call_args.args[0]]
        self.assertEqual(argv[1:4], ["context", "create", "lima-docker"])
        self.assertEqual(argv[-1], f"host=unix://{self.docker.SOCKET}")


class Fragment(unittest.TestCase):
    def test_owned_keys_select_the_managed_context_and_plugin_dir(self):
        fragment = json.loads((RITE_DIR / "config.json").read_text())
        self.assertEqual(fragment["currentContext"], _load().CONTEXT)
        self.assertIn(
            "/opt/homebrew/lib/docker/cli-plugins", fragment["cliPluginsExtraDirs"]
        )
