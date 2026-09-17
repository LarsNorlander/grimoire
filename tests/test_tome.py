"""Tests for the op engine: copy, write, link, accept, and key registration.

Hooks are not exercised here — they shell out to installers. The CLI tests
cover them through `cast --dry-run`.

Run with: uv run python -m unittest
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from arcana.manifest import Manifest
from arcana.tome import RiteContext


class Root(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name, "root")
        self.rite_dir = self.root / "rites" / "t"
        self.rite_dir.mkdir(parents=True)
        self.home = Path(self.tmp.name, "home")
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, name: str, text: str) -> Path:
        p = self.rite_dir / name
        p.write_text(text)
        return p

    def tome(self, name: str) -> Path:
        return self.root / "tome" / "t" / name

    def run_ctx(self, register, *, force=False, accepting=False, dry_run=False) -> str:
        ctx = RiteContext("work", self.root, "t", force=force, accepting=accepting)
        register(ctx)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ctx.execute(dry_run=dry_run)
        return buf.getvalue()

    def manifest(self) -> Manifest:
        return Manifest.load(self.root / "tome")


class Copy(Root):
    def test_builds_tome_and_records_hash(self):
        self.source("a", "one\n")
        out = self.run_ctx(lambda c: c.copy("a"))
        self.assertIn("built tome/t/a", out)
        self.assertEqual(self.tome("a").read_text(), "one\n")
        self.assertIn("t/a", self.manifest())

    def test_skips_externally_modified_unless_forced(self):
        self.source("a", "one\n")
        self.run_ctx(lambda c: c.copy("a"))
        self.tome("a").write_text("edited\n")
        out = self.run_ctx(lambda c: c.copy("a"))
        self.assertIn("SKIPPED", out)
        self.assertEqual(self.tome("a").read_text(), "edited\n")
        self.run_ctx(lambda c: c.copy("a"), force=True)
        self.assertEqual(self.tome("a").read_text(), "one\n")

    def test_dry_run_touches_nothing(self):
        self.source("a", "one\n")
        out = self.run_ctx(lambda c: c.copy("a"), dry_run=True)
        self.assertIn("[dry-run] copy", out)
        self.assertFalse(self.tome("a").exists())
        self.assertEqual(len(self.manifest()), 0)


class Write(Root):
    def test_builder_receives_context_kwargs(self):
        seen = {}

        def build(**kw):
            seen.update(kw)
            return "generated\n"

        self.run_ctx(lambda c: c.write("g", build))
        self.assertEqual(seen, {"profile": "work", "rite_dir": self.rite_dir, "grimoire_root": self.root})
        self.assertEqual(self.tome("g").read_text(), "generated\n")
        self.assertIn("t/g", self.manifest())

    def test_static_content_and_skip_rule(self):
        self.run_ctx(lambda c: c.write("g", "v1\n"))
        self.tome("g").write_text("edited\n")
        out = self.run_ctx(lambda c: c.write("g", "v2\n"))
        self.assertIn("SKIPPED", out)
        self.assertEqual(self.tome("g").read_text(), "edited\n")

    def test_accept_mode_warns_and_never_calls_builder(self):
        def build(**_):
            raise AssertionError("builder must not run in accept mode")

        out = self.run_ctx(lambda c: c.write("g", build), accepting=True)
        self.assertIn("needs manual reconciliation", out)


class Link(Root):
    def register(self, c):
        c.copy("a")
        c.link("a", str(self.home / ".config" / "a"))

    def test_creates_then_stays_quiet_when_correct(self):
        self.source("a", "x\n")
        out = self.run_ctx(self.register)
        dest = self.home / ".config" / "a"
        self.assertIn("created", out)
        self.assertEqual(dest.readlink(), self.tome("a"))
        self.assertEqual(self.manifest().get("t/a").links, [str(dest)])
        out = self.run_ctx(self.register)
        self.assertNotIn(str(dest), out)

    def test_link_list_is_replaced_each_cast(self):
        self.source("a", "x\n")
        self.run_ctx(self.register)
        self.run_ctx(lambda c: c.copy("a"))  # same file, no link registered this pass
        self.assertEqual(self.manifest().get("t/a").links, [])

    def test_repoints_a_stale_symlink(self):
        self.source("a", "x\n")
        dest = self.home / ".config" / "a"
        dest.parent.mkdir()
        dest.symlink_to(self.home / "elsewhere")
        out = self.run_ctx(self.register)
        self.assertIn("updated", out)
        self.assertEqual(dest.readlink(), self.tome("a"))

    def test_refuses_to_replace_a_real_file(self):
        self.source("a", "x\n")
        dest = self.home / ".config" / "a"
        dest.parent.mkdir()
        dest.write_text("precious\n")
        out = self.run_ctx(self.register)
        self.assertIn("ERROR", out)
        self.assertFalse(dest.is_symlink())
        self.assertEqual(dest.read_text(), "precious\n")

    def test_link_is_inert_in_accept_mode(self):
        self.source("a", "x\n")
        self.run_ctx(lambda c: c.copy("a"))
        self.run_ctx(self.register, accepting=True)
        self.assertFalse((self.home / ".config" / "a").exists())


class Accept(Root):
    def test_copies_tome_back_and_resets_baseline(self):
        self.source("a", "one\n")
        self.run_ctx(lambda c: c.copy("a"))
        self.tome("a").write_text("two\n")
        out = self.run_ctx(lambda c: c.copy("a"), accepting=True)
        self.assertIn("accepted t/a", out)
        self.assertEqual((self.rite_dir / "a").read_text(), "two\n")
        out = self.run_ctx(lambda c: c.copy("a"))
        self.assertNotIn("SKIPPED", out)

    def test_noop_when_unmodified_and_when_source_missing(self):
        self.source("a", "one\n")
        self.run_ctx(lambda c: c.copy("a"))
        self.assertIn("not modified", self.run_ctx(lambda c: c.copy("a"), accepting=True))
        (self.rite_dir / "a").unlink()
        self.tome("a").write_text("two\n")
        self.assertIn("no matching source", self.run_ctx(lambda c: c.copy("a"), accepting=True))

    def test_refuses_secrets_and_leaves_source_untouched(self):
        self.source("a", "clean\n")
        self.run_ctx(lambda c: c.copy("a"))
        self.tome("a").write_text("aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n")
        with self.assertRaises(SystemExit):
            self.run_ctx(lambda c: c.copy("a"), accepting=True)
        self.assertEqual((self.rite_dir / "a").read_text(), "clean\n")


class Hook(Root):
    def test_runs_unless_guard_says_done(self):
        ran = []
        self.run_ctx(lambda c: c.hook("h", lambda: ran.append(1), unless=lambda: False))
        self.run_ctx(lambda c: c.hook("h", lambda: ran.append(1), unless=lambda: True))
        self.run_ctx(lambda c: c.hook("h", lambda: ran.append(1)))
        self.assertEqual(ran, [1, 1])

    def test_dry_run_reports_guard_state_without_running(self):
        ran = []
        out = self.run_ctx(lambda c: c.hook("h", lambda: ran.append(1), unless=lambda: True), dry_run=True)
        self.assertIn("already done, would skip", out)
        out = self.run_ctx(lambda c: c.hook("h", lambda: ran.append(1)), dry_run=True)
        self.assertIn("would run", out)
        self.assertEqual(ran, [])

    def test_hook_is_inert_in_accept_mode(self):
        ran = []
        self.run_ctx(lambda c: c.hook("h", lambda: ran.append(1)), accepting=True)
        self.assertEqual(ran, [])


class Registration(Root):
    def test_registered_keys_cover_only_file_producing_ops(self):
        ctx = RiteContext("work", self.root, "t")
        ctx.copy("a", "b")
        ctx.write("g", "x")
        ctx.patch("p.json", str(self.home / "p.json"))
        ctx.link("a", str(self.home / "a"))
        ctx.hook("noop", lambda: None)
        ctx.doc(lambda **_: None)
        self.assertEqual(ctx.registered_keys(), {"t/a", "t/b", "t/g", "t/p.json"})


if __name__ == "__main__":
    unittest.main()
