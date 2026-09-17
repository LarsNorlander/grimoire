"""Tests for arcana.rites: discovery, the profile gate, and manifest GC.

Run with: uv run python -m unittest
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from arcana import rites
from arcana.tome import RiteSkipped, load_manifest, save_manifest

RITE = """#!/usr/bin/env python3
{directive}from arcana.tome import RiteContext
ctx = RiteContext.from_args()
ctx.copy({files})
"""


class Root(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def add_rite(self, tool: str, *files: str, profile: str | None = None,
                 executable: bool = True) -> Path:
        d = self.root / "rites" / tool
        d.mkdir(parents=True)
        for f in files:
            (d / f).write_text(f"{f}\n")
        path = d / "rite"
        directive = f"# profile: {profile}\n" if profile else ""
        path.write_text(RITE.format(directive=directive, files=", ".join(repr(f) for f in files)))
        path.chmod(0o755 if executable else 0o644)
        return path

    def tome(self, key: str) -> Path:
        tool, filename = key.split("/", 1)
        p = self.root / "tome" / tool / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("built\n")
        return p


class Discovery(Root):
    def test_all_rites_sorted_and_executable_only(self):
        self.add_rite("b", "x")
        self.add_rite("a", "x")
        self.add_rite("parked", "x", executable=False)
        self.assertEqual([p.parent.name for p in rites.discover(self.root)], ["a", "b"])

    def test_named_rite_must_exist(self):
        self.add_rite("a", "x")
        self.assertEqual(len(rites.discover(self.root, ("a",))), 1)
        with self.assertRaises(rites.RiteNotFound) as cm:
            rites.discover(self.root, ("a", "missing"))
        self.assertEqual(cm.exception.tool, "missing")


class Loading(Root):
    def test_profile_gate_raises_before_import_unless_accepting(self):
        path = self.add_rite("t", "x", profile="personal")
        with self.assertRaises(RiteSkipped):
            rites.load_rite(path, "work", self.root)
        ctx = rites.load_rite(path, "work", self.root, accepting=True)
        self.assertEqual(ctx.registered_keys(), {"t/x"})
        self.assertTrue(rites.allowed_under(path, "personal"))
        self.assertFalse(rites.allowed_under(path, "work"))

    def test_loaded_context_registers_ops_without_executing(self):
        path = self.add_rite("t", "x", "y")
        ctx = rites.load_rite(path, "work", self.root)
        self.assertEqual(ctx.registered_keys(), {"t/x", "t/y"})
        self.assertFalse((self.root / "tome").exists())


class ManifestGC(Root):
    def gc(self, touched, built) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rites.gc_manifest(self.root, touched, built)
        return buf.getvalue()

    def test_prunes_file_a_rite_stopped_managing(self):
        self.add_rite("t", "x")
        kept, dropped = self.tome("t/x"), self.tome("t/old")
        save_manifest(self.root / "tome", {"t/x": "h", "t/old": "h"})
        out = self.gc(touched={"t/x"}, built={"t"})
        self.assertIn("t/old", out)
        self.assertEqual(set(load_manifest(self.root / "tome")), {"t/x"})
        self.assertTrue(kept.exists())
        self.assertFalse(dropped.exists())

    def test_prunes_removed_tool_and_flags_dangling_links(self):
        self.add_rite("keep", "x")
        self.tome("keep/x"); self.tome("gone/x")
        save_manifest(self.root / "tome", {"keep/x": "h", "gone/x": "h"})
        out = self.gc(touched={"keep/x"}, built={"keep"})
        self.assertEqual(set(load_manifest(self.root / "tome")), {"keep/x"})
        self.assertFalse((self.root / "tome" / "gone").exists())
        self.assertIn("gone", out)
        self.assertIn("dangling", out)

    def test_preserves_entries_of_profile_skipped_rites(self):
        self.add_rite("skipped", "x", profile="personal")
        self.add_rite("ran", "x")
        self.tome("skipped/x"); self.tome("ran/x")
        save_manifest(self.root / "tome", {"skipped/x": "h", "ran/x": "h"})
        out = self.gc(touched={"ran/x"}, built={"ran"})
        self.assertEqual(out, "")
        self.assertEqual(set(load_manifest(self.root / "tome")), {"skipped/x", "ran/x"})


if __name__ == "__main__":
    unittest.main()
