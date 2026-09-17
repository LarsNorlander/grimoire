"""Tests for the manifest: round trip, legacy migration, and entry updates.

Run with: uv run python -m unittest
"""

import json
import tempfile
import unittest
from pathlib import Path

from arcana.manifest import Entry, Manifest


class Persistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tome = Path(self.tmp.name, "tome")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_is_an_empty_manifest(self):
        m = Manifest.load(self.tome)
        self.assertEqual(len(m), 0)
        self.assertIsNone(m.hash("x/y"))

    def test_round_trip_preserves_every_field(self):
        m = Manifest.load(self.tome)
        m.record("t/a", "h1", "copy")
        m.set_links("t/a", ["/home/b", "/home/a"])
        m.record("t/p.json", "h2", "patch")
        m.set_target("t/p.json", "/home/p.json")
        m.save()

        again = Manifest.load(self.tome)
        self.assertEqual(
            again.get("t/a"),
            Entry(hash="h1", kind="copy", links=["/home/a", "/home/b"]),
        )
        self.assertEqual(
            again.get("t/p.json"), Entry(hash="h2", kind="patch", target="/home/p.json")
        )
        data = json.loads((self.tome / ".manifest").read_text())
        self.assertEqual(data["version"], 2)
        self.assertNotIn(
            "links", data["files"]["t/p.json"], "empty optionals are omitted"
        )

    def test_legacy_lines_are_read_and_rewritten_as_v2(self):
        self.tome.mkdir()
        (self.tome / ".manifest").write_text("t/a=h1\nt/b=h2\n")
        m = Manifest.load(self.tome)
        self.assertEqual(m.keys(), ["t/a", "t/b"])
        self.assertEqual(m.get("t/a"), Entry(hash="h1"))
        m.save()
        self.assertTrue((self.tome / ".manifest").read_text().lstrip().startswith("{"))
        self.assertEqual(Manifest.load(self.tome).hash("t/b"), "h2")

    def test_record_keeps_links_and_target_across_rebuilds(self):
        m = Manifest.load(self.tome)
        m.record("t/a", "h1", "copy")
        m.set_links("t/a", ["/home/a"])
        m.record("t/a", "h2", "copy")
        self.assertEqual(m.get("t/a"), Entry(hash="h2", kind="copy", links=["/home/a"]))

    def test_links_and_target_ignore_unknown_keys(self):
        m = Manifest.load(self.tome)
        m.set_links("nope", ["/x"])
        m.set_target("nope", "/x")
        self.assertEqual(len(m), 0)

    def test_remove_returns_the_entry(self):
        m = Manifest.load(self.tome)
        m.record("t/a", "h", "copy")
        self.assertEqual(m.remove("t/a"), Entry(hash="h", kind="copy"))
        self.assertIsNone(m.remove("t/a"))
        self.assertNotIn("t/a", m)


if __name__ == "__main__":
    unittest.main()
