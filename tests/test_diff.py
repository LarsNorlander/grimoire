"""Table test over the diff status matrix.

Each row is one state of (rite source, tome, manifest, target) for one op
kind, with the three statuses `compute_diff` must report and whether the pair
counts as a conflict. A wrong status here silently misleads `grimoire diff`.

Run with: uv run python -m unittest
"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from arcana import diff
from arcana import patch
from arcana.diff import Direction as D, Status as S
from arcana.manifest import Entry, Manifest
from arcana.tome import RiteContext


class Matrix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name, "root")
        self.rite_dir = self.root / "rites" / "t"
        self.rite_dir.mkdir(parents=True)
        self.tome_dir = self.root / "tome" / "t"
        self.tome_dir.mkdir(parents=True)
        self.target = Path(self.tmp.name, "live.json")

    def tearDown(self):
        self.tmp.cleanup()

    # -- state builders -------------------------------------------------

    @staticmethod
    def sha(b: bytes) -> str:
        return hashlib.sha256(b).hexdigest()

    def plan(self, register, build=False) -> diff.FilePlan:
        ctx = RiteContext("work", self.root, "t")
        register(ctx)
        (p,) = diff.plan_rite(ctx, build=build)
        return p

    def manifest(self, entries: dict) -> Manifest:
        return Manifest(self.root / "tome" / ".manifest",
                        {k: Entry(hash=v) for k, v in entries.items()})

    def check(self, result: diff.DiffResult, drift, cast, accept, conflict=False):
        self.assertEqual(result.statuses, {D.DRIFT: drift, D.CAST: cast, D.ACCEPT: accept})
        self.assertIs(result.has_conflict, conflict)

    # -- copy() -----------------------------------------------------------

    def copy_case(self, *, source, tome, manifest_of):
        if source is not None:
            (self.rite_dir / "a").write_bytes(source)
        if tome is not None:
            (self.tome_dir / "a").write_bytes(tome)
        manifest = self.manifest({"t/a": self.sha(manifest_of)} if manifest_of is not None else {})
        return diff.compute_diff(self.plan(lambda c: c.copy("a")), manifest, build=False)

    def test_copy_clean(self):
        r = self.copy_case(source=b"v1", tome=b"v1", manifest_of=b"v1")
        self.check(r, S.CLEAN, S.CLEAN, S.CLEAN)

    def test_copy_live_edit(self):
        r = self.copy_case(source=b"v1", tome=b"edit", manifest_of=b"v1")
        self.check(r, S.MODIFIED, S.MODIFIED, S.MODIFIED, conflict=True)

    def test_copy_source_edit_pending_cast(self):
        r = self.copy_case(source=b"v2", tome=b"v1", manifest_of=b"v1")
        self.check(r, S.CLEAN, S.MODIFIED, S.MODIFIED)

    def test_copy_never_cast(self):
        r = self.copy_case(source=b"v1", tome=None, manifest_of=None)
        self.check(r, S.CLEAN, S.ADDED, S.CLEAN)

    def test_copy_tome_deleted_after_cast(self):
        r = self.copy_case(source=b"v1", tome=None, manifest_of=b"v1")
        self.check(r, S.DELETED, S.ADDED, S.CLEAN, conflict=True)

    def test_copy_tome_present_without_manifest(self):
        r = self.copy_case(source=b"v1", tome=b"v1", manifest_of=None)
        self.check(r, S.ADDED, S.CLEAN, S.CLEAN)

    def test_copy_source_missing(self):
        r = self.copy_case(source=None, tome=b"v1", manifest_of=b"v1")
        self.check(r, S.CLEAN, S.DELETED, S.DELETED)

    # -- write() ----------------------------------------------------------

    def write_case(self, *, content, tome, manifest_of, build):
        if tome is not None:
            (self.tome_dir / "g").write_bytes(tome)
        manifest = self.manifest({"t/g": self.sha(manifest_of)} if manifest_of is not None else {})
        plan = self.plan(lambda c: c.write("g", lambda **_: content), build=build)
        return diff.compute_diff(plan, manifest, build=build)

    def test_write_unevaluated_without_build(self):
        r = self.write_case(content="v1", tome=b"v1", manifest_of=b"v1", build=False)
        self.check(r, S.CLEAN, S.UNEVALUATED, S.NA)

    def test_write_built_clean_and_pending(self):
        r = self.write_case(content="v1", tome=b"v1", manifest_of=b"v1", build=True)
        self.check(r, S.CLEAN, S.CLEAN, S.NA)
        r = self.write_case(content="v2", tome=b"v1", manifest_of=b"v1", build=True)
        self.check(r, S.CLEAN, S.MODIFIED, S.NA)

    def test_write_live_edit_is_never_acceptable(self):
        r = self.write_case(content="v1", tome=b"edit", manifest_of=b"v1", build=True)
        self.check(r, S.MODIFIED, S.MODIFIED, S.NA, conflict=True)

    # -- patch() ----------------------------------------------------------

    def patch_case(self, *, fragment, applied, live, manifest_of):
        """`applied` is the last-cast fragment (tome); `live` the target document."""
        if fragment is not None:
            (self.rite_dir / "f.json").write_text(json.dumps(fragment))
        if applied is not None:
            (self.tome_dir / "f.json").write_bytes(patch.canonical(applied))
        if live is not None:
            self.target.write_text(json.dumps(live))
        manifest = self.manifest(
            {"t/f.json": self.sha(patch.canonical(manifest_of))} if manifest_of is not None else {})
        plan = self.plan(lambda c: c.patch("f.json", str(self.target)))
        return diff.compute_diff(plan, manifest, build=False)

    def test_patch_clean_ignores_unowned_keys(self):
        f = {"tui": "full"}
        r = self.patch_case(fragment=f, applied=f, live={"tui": "full", "model": "anything"}, manifest_of=f)
        self.check(r, S.CLEAN, S.CLEAN, S.CLEAN)

    def test_patch_owned_key_edited_live(self):
        f = {"tui": "full"}
        r = self.patch_case(fragment=f, applied=f, live={"tui": "compact"}, manifest_of=f)
        self.check(r, S.MODIFIED, S.MODIFIED, S.MODIFIED, conflict=True)

    def test_patch_fragment_gains_key_is_pending_cast_only(self):
        applied = {"tui": "full"}
        r = self.patch_case(fragment={"tui": "full", "effort": "high"}, applied=applied,
                            live={"tui": "full"}, manifest_of=applied)
        self.check(r, S.CLEAN, S.MODIFIED, S.MODIFIED)

    def test_patch_target_missing_after_cast(self):
        f = {"tui": "full"}
        r = self.patch_case(fragment=f, applied=f, live=None, manifest_of=f)
        self.check(r, S.DELETED, S.ADDED, S.CLEAN, conflict=True)

    def test_patch_never_cast(self):
        r = self.patch_case(fragment={"tui": "full"}, applied=None, live={"model": "x"}, manifest_of=None)
        # Nothing applied yet: same row as a never-cast copy() file.
        self.check(r, S.CLEAN, S.ADDED, S.CLEAN)

    def test_patch_unreadable_target_reads_as_missing(self):
        f = {"tui": "full"}
        self.target.write_text("{broken")
        r = self.patch_case(fragment=f, applied=f, live=None, manifest_of=f)
        self.check(r, S.DELETED, S.ADDED, S.CLEAN, conflict=True)

    # -- formatting ------------------------------------------------------

    def test_summary_labels_kind_and_counts_conflicts(self):
        f = {"tui": "full"}
        r = self.patch_case(fragment=f, applied=f, live={"tui": "compact"}, manifest_of=f)
        text = diff.format_summary([r], set(D))
        self.assertIn("t/f.json  [patch()]", text)
        self.assertIn("owned keys in target changed", text)
        self.assertIn("1 potential conflict", text)
        self.assertTrue(r.is_clean_in(set()) and not r.is_clean_in({D.DRIFT}))


if __name__ == "__main__":
    unittest.main()
