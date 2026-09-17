"""Tests for patch(): the pure helpers and the cast/accept round trip.

Run with: uv run python -m unittest
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from arcana import patch
from arcana.manifest import Manifest
from arcana.tome import RiteContext


class Helpers(unittest.TestCase):
    def test_leaves_traverse_dicts_and_stop_at_arrays(self):
        frag = {"a": {"b": 1, "c": [1, 2]}, "d": "x", "e": {}}
        self.assertEqual(
            patch.leaves(frag),
            [("a", "b"), ("a", "c"), ("d",), ("e",)],
        )

    def test_extract_reports_missing_paths(self):
        doc = {"a": {"b": 1}, "d": "x"}
        frag, missing = patch.extract(doc, [("a", "b"), ("a", "zz"), ("q",)])
        self.assertEqual(frag, {"a": {"b": 1}})
        self.assertEqual(missing, [("a", "zz"), ("q",)])

    def test_merge_replaces_arrays_and_keeps_unowned_keys(self):
        doc = {"perm": {"allow": ["old"], "mode": "ask"}, "model": "opus"}
        frag = {"perm": {"allow": ["new"]}}
        out = patch.merge(doc, frag)
        self.assertEqual(
            out, {"perm": {"allow": ["new"], "mode": "ask"}, "model": "opus"}
        )
        self.assertEqual(doc["perm"]["allow"], ["old"], "merge must not mutate input")

    def test_prune_drops_paths_and_emptied_parents(self):
        doc = {"a": {"b": 1, "c": 2}, "x": {"y": {"z": 3}}, "keep": 1}
        out = patch.prune(doc, [("a", "b"), ("x", "y", "z")])
        self.assertEqual(out, {"a": {"c": 2}, "keep": 1})
        self.assertIn("x", doc, "prune must not mutate input")

    def test_canonical_is_order_independent(self):
        self.assertEqual(
            patch.canonical({"b": 1, "a": 2}), patch.canonical({"a": 2, "b": 1})
        )

    def test_load_rejects_non_object_and_bad_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "x.json")
            p.write_text("[1]")
            with self.assertRaises(ValueError):
                patch.load(p)
            p.write_text("{nope")
            with self.assertRaises(ValueError):
                patch.load(p)


class RoundTrip(unittest.TestCase):
    """Drive RiteContext directly against a temp grimoire root and target."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name, "grimoire")
        self.rite_dir = self.root / "rites" / "tool"
        self.rite_dir.mkdir(parents=True)
        self.target = Path(self.tmp.name, "live", "settings.json")
        self.target.parent.mkdir()
        self.source = self.rite_dir / "fragment.json"

    def tearDown(self):
        self.tmp.cleanup()

    def ctx(self, *, force=False, accepting=False):
        c = RiteContext("work", self.root, "tool", force=force, accepting=accepting)
        c.patch("fragment.json", str(self.target))
        return c

    def run_ctx(self, **kw) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.ctx(**kw).execute()
        return buf.getvalue()

    def write_source(self, frag):
        self.source.write_text(json.dumps(frag, indent=2) + "\n")

    def read_target(self):
        return json.loads(self.target.read_text())

    def test_cast_merges_into_existing_file_and_creates_when_missing(self):
        self.write_source({"perm": {"allow": ["a"]}, "tui": "full"})
        self.target.write_text(json.dumps({"model": "opus", "perm": {"mode": "ask"}}))
        out = self.run_ctx()
        self.assertIn("patched", out)
        self.assertEqual(
            self.read_target(),
            {"model": "opus", "perm": {"mode": "ask", "allow": ["a"]}, "tui": "full"},
        )
        entry = Manifest.load(self.root / "tome").get("tool/fragment.json")
        assert entry is not None
        self.assertEqual((entry.kind, entry.target), ("patch", str(self.target)))

        self.target.unlink()
        self.run_ctx()
        self.assertEqual(self.read_target(), {"perm": {"allow": ["a"]}, "tui": "full"})

    def test_unowned_edits_are_not_drift(self):
        self.write_source({"tui": "full"})
        self.target.write_text("{}")
        self.run_ctx()
        doc = self.read_target()
        doc["model"] = "changed-by-app"
        self.target.write_text(json.dumps(doc))
        out = self.run_ctx()
        self.assertIn("patched", out)
        self.assertNotIn("SKIPPED", out)
        self.assertEqual(self.read_target()["model"], "changed-by-app")

    def test_owned_edit_skips_cast_unless_forced(self):
        self.write_source({"tui": "full"})
        self.target.write_text("{}")
        self.run_ctx()
        doc = self.read_target()
        doc["tui"] = "compact"
        self.target.write_text(json.dumps(doc))
        out = self.run_ctx()
        self.assertIn("SKIPPED", out)
        self.assertEqual(self.read_target()["tui"], "compact")
        self.run_ctx(force=True)
        self.assertEqual(self.read_target()["tui"], "full")

    def test_removed_source_key_is_pruned_from_target(self):
        self.write_source({"a": {"b": 1, "c": 2}})
        self.target.write_text("{}")
        self.run_ctx()
        self.write_source({"a": {"c": 2}})
        out = self.run_ctx()
        self.assertIn("pruned 1", out)
        self.assertEqual(self.read_target(), {"a": {"c": 2}})

    def test_accept_pulls_owned_keys_and_keeps_missing_source_values(self):
        self.write_source({"perm": {"allow": ["a"]}, "tui": "full"})
        self.target.write_text("{}")
        self.run_ctx()
        doc = self.read_target()
        doc["perm"]["allow"] = ["a", "b"]
        del doc["tui"]
        doc["model"] = "ignored"
        self.target.write_text(json.dumps(doc))
        out = self.run_ctx(accepting=True)
        self.assertIn("accepted", out)
        self.assertIn("tui missing from target", out)
        self.assertEqual(
            json.loads(self.source.read_text()),
            {"perm": {"allow": ["a", "b"]}, "tui": "full"},
        )
        # Accept resets the baseline: a following cast is clean, not skipped.
        self.assertNotIn("SKIPPED", self.run_ctx())

    def test_accept_is_noop_when_owned_keys_unchanged(self):
        self.write_source({"tui": "full"})
        self.target.write_text(json.dumps({"model": "x"}))
        self.run_ctx()
        out = self.run_ctx(accepting=True)
        self.assertIn("not modified", out)

    def test_migrating_from_link_materializes_target_and_prunes_nothing(self):
        # Yesterday's rite copied and linked the whole file.
        old = {"theme": "light", "lastChangelogVersion": "0.85.1", "extra": 1}
        self.source.write_text(json.dumps(old))
        c = RiteContext("work", self.root, "tool")
        c.copy("fragment.json")
        c.link("fragment.json", str(self.target))
        with redirect_stdout(io.StringIO()):
            c.execute()
        self.assertTrue(self.target.is_symlink())

        # Today's rite owns only the theme.
        self.write_source({"theme": "dark"})
        out = self.run_ctx()
        self.assertIn("materialized", out)
        self.assertFalse(self.target.is_symlink())
        self.assertEqual(
            self.read_target(),
            {"theme": "dark", "lastChangelogVersion": "0.85.1", "extra": 1},
        )
        self.assertNotIn("pruned", out)
        self.assertEqual(
            json.loads((self.root / "tome/tool/fragment.json").read_text()),
            {"theme": "dark"},
        )

    def test_symlink_to_elsewhere_is_refused(self):
        self.write_source({"theme": "dark"})
        other = Path(self.tmp.name, "elsewhere.json")
        other.write_text("{}")
        self.target.symlink_to(other)
        out = self.run_ctx()
        self.assertIn("ERROR", out)
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(other.read_text(), "{}")

    def test_invalid_target_is_reported_not_clobbered(self):
        self.write_source({"tui": "full"})
        self.target.write_text("{broken")
        out = self.run_ctx()
        self.assertIn("ERROR", out)
        self.assertEqual(self.target.read_text(), "{broken")


if __name__ == "__main__":
    unittest.main()
