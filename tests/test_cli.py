"""CLI-level tests: real verbs against a throwaway root.

`GRIMOIRE_ROOT` and `GRIMOIRE_PROFILE_FILE` are read at import, so each verb
runs in a subprocess with the overrides in its environment. Nothing here
touches ~/.grimoire or the machine's profile.

Run with: uv run python -m unittest
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

RITE = """#!/usr/bin/env python3
from arcana.tome import RiteContext
ctx = RiteContext.from_args()
ctx.copy("config")
ctx.link("config", "{target}")
"""


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "root"
        self.profile_file = base / "profile"
        self.profile_file.write_text("work\n")
        self.target = base / "home" / ".config" / "tool" / "config"
        rite_dir = self.root / "rites" / "tool"
        rite_dir.mkdir(parents=True)
        (rite_dir / "config").write_text("setting = 1\n")
        rite = rite_dir / "rite"
        rite.write_text(RITE.format(target=self.target))
        rite.chmod(0o755)
        # `_ensure_prerequisites` syncs the root's venv when it looks stale.
        # A data-only root has nothing to sync, so make it look fresh.
        (self.root / "uv.lock").touch()
        (self.root / ".venv").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def grimoire(self, *args: str) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "GRIMOIRE_ROOT": str(self.root),
            "GRIMOIRE_PROFILE_FILE": str(self.profile_file),
            "PYTHONPATH": str(REPO),
        }
        return subprocess.run(
            [sys.executable, "-m", "arcana.cli", *args],
            cwd=REPO, env=env, capture_output=True, text=True,
        )

    def manifest(self) -> dict:
        return dict(
            line.split("=", 1)
            for line in (self.root / "tome" / ".manifest").read_text().splitlines()
        )


class Verbs(Harness):
    def test_cast_builds_tome_links_target_and_records_manifest(self):
        r = self.grimoire("cast")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"from {self.root}", r.stdout)
        self.assertEqual((self.root / "tome" / "tool" / "config").read_text(), "setting = 1\n")
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(self.target.resolve(), (self.root / "tome" / "tool" / "config").resolve())
        self.assertIn("tool/config", self.manifest())

    def test_diff_exit_code_tracks_drift(self):
        self.grimoire("cast")
        self.assertEqual(self.grimoire("diff").returncode, 0)
        (self.root / "tome" / "tool" / "config").write_text("setting = 2\n")
        r = self.grimoire("diff")
        self.assertEqual(r.returncode, 1)
        self.assertIn("tool/config", r.stdout)
        self.assertIn("potential conflict", r.stdout)

    def test_cast_skips_externally_modified_tome_unless_forced(self):
        self.grimoire("cast")
        tome_file = self.root / "tome" / "tool" / "config"
        tome_file.write_text("setting = 2\n")
        r = self.grimoire("cast")
        self.assertIn("SKIPPED", r.stdout)
        self.assertEqual(tome_file.read_text(), "setting = 2\n")
        self.grimoire("cast", "--force")
        self.assertEqual(tome_file.read_text(), "setting = 1\n")

    def test_accept_round_trips_copy_file(self):
        self.grimoire("cast")
        (self.root / "tome" / "tool" / "config").write_text("setting = 3\n")
        r = self.grimoire("accept", "tool")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.root / "rites" / "tool" / "config").read_text(), "setting = 3\n")
        self.assertEqual(self.grimoire("diff").returncode, 0)

    def test_full_cast_prunes_manifest_when_rite_is_removed(self):
        self.grimoire("cast")
        for p in (self.root / "rites" / "tool").iterdir():
            p.unlink()
        (self.root / "rites" / "tool").rmdir()
        # Another rite keeps the run a full, successful cast.
        other = self.root / "rites" / "other"
        other.mkdir()
        (other / "config").write_text("x\n")
        (other / "rite").write_text(RITE.format(target=Path(self.tmp.name, "home", "other")))
        (other / "rite").chmod(0o755)
        r = self.grimoire("cast")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Pruning stale manifest entries", r.stdout)
        self.assertNotIn("tool/config", self.manifest())
        self.assertFalse((self.root / "tome" / "tool").exists())

    def test_profile_gate_skips_rite(self):
        rite = self.root / "rites" / "tool" / "rite"
        rite.write_text(rite.read_text().replace(
            "#!/usr/bin/env python3\n", "#!/usr/bin/env python3\n# profile: personal\n", 1))
        r = self.grimoire("cast")
        self.assertIn("skipped tool", r.stdout)
        self.assertFalse((self.root / "tome" / "tool").exists())

    def test_diff_without_profile_exits_2(self):
        self.profile_file.unlink()
        r = self.grimoire("diff")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no profile set", r.stderr)


if __name__ == "__main__":
    unittest.main()
