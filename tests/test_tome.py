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
        self.assertEqual(
            seen,
            {"profile": "work", "rite_dir": self.rite_dir, "grimoire_root": self.root},
        )
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
        entry = self.manifest().get("t/a")
        assert entry is not None
        self.assertEqual(entry.links, [str(dest)])
        out = self.run_ctx(self.register)
        self.assertNotIn(str(dest), out)

    def test_link_list_is_replaced_each_cast(self):
        self.source("a", "x\n")
        self.run_ctx(self.register)
        self.run_ctx(lambda c: c.copy("a"))  # same file, no link registered this pass
        entry = self.manifest().get("t/a")
        assert entry is not None
        self.assertEqual(entry.links, [])

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
        self.assertIn(
            "not modified", self.run_ctx(lambda c: c.copy("a"), accepting=True)
        )
        (self.rite_dir / "a").unlink()
        self.tome("a").write_text("two\n")
        self.assertIn(
            "no matching source", self.run_ctx(lambda c: c.copy("a"), accepting=True)
        )

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
        out = self.run_ctx(
            lambda c: c.hook("h", lambda: ran.append(1), unless=lambda: True),
            dry_run=True,
        )
        self.assertIn("already done, would skip", out)
        out = self.run_ctx(lambda c: c.hook("h", lambda: ran.append(1)), dry_run=True)
        self.assertIn("would run", out)
        self.assertEqual(ran, [])

    def test_hook_is_inert_in_accept_mode(self):
        ran = []
        self.run_ctx(lambda c: c.hook("h", lambda: ran.append(1)), accepting=True)
        self.assertEqual(ran, [])


class Install(Root):
    """install(): real files under a live folder, one manifest entry each."""

    def setUp(self):
        super().setUp()
        self.live = self.home / "mods" / "m"

    def ship(self, rel: str, text: str) -> Path:
        p = self.rite_dir / "m" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def install(self, c):
        c.install("m", str(self.live))

    def test_exclude_skips_matching_files_by_name_or_path(self):
        self.ship("main.js", "one\n")
        self.ship("gpui-kit.d.ts", "types\n")
        self.ship("lib/jsconfig.json", "{}\n")
        self.ship("lib/keep.json", "{}\n")
        ctx = RiteContext("work", self.root, "t")
        ctx.install("m", str(self.live), exclude=("*.d.ts", "lib/jsconfig.json"))
        self.assertEqual(ctx.registered_keys(), {"t/m/main.js", "t/m/lib/keep.json"})
        self.run_ctx(
            lambda c: c.install(
                "m", str(self.live), exclude=("*.d.ts", "lib/jsconfig.json")
            )
        )
        self.assertFalse((self.live / "gpui-kit.d.ts").exists())
        self.assertFalse((self.live / "lib" / "jsconfig.json").exists())
        self.assertTrue((self.live / "lib" / "keep.json").exists())

    def test_installs_real_files_and_records_target_and_root(self):
        self.ship("main.js", "one\n")
        self.ship("lib/util.js", "two\n")
        self.ship(".DS_Store", "junk")
        out = self.run_ctx(self.install)
        main, util = self.live / "main.js", self.live / "lib" / "util.js"
        self.assertIn(f"installed {main}", out)
        self.assertFalse(main.is_symlink())
        self.assertEqual(main.read_text(), "one\n")
        self.assertEqual(util.read_text(), "two\n")
        self.assertFalse((self.live / ".DS_Store").exists())
        self.assertFalse((self.root / "tome" / "t").exists(), "nothing in tome")
        entry = self.manifest().get("t/m/lib/util.js")
        self.assertEqual(
            (entry.kind, entry.target, entry.root),
            ("install", str(util), str(self.live)),
        )
        self.assertNotIn(".grimoire", " ".join(p.name for p in self.live.iterdir()))

    def test_repeat_cast_is_quiet_and_source_edits_update(self):
        src = self.ship("main.js", "one\n")
        self.run_ctx(self.install)
        self.assertEqual(self.run_ctx(self.install), "")
        src.write_text("two\n")
        out = self.run_ctx(self.install)
        self.assertIn("installed", out)
        self.assertEqual((self.live / "main.js").read_text(), "two\n")

    def test_skips_live_edit_unless_forced(self):
        src = self.ship("main.js", "one\n")
        self.run_ctx(self.install)
        (self.live / "main.js").write_text("edited\n")
        src.write_text("two\n")
        out = self.run_ctx(self.install)
        self.assertIn("SKIPPED", out)
        self.assertEqual((self.live / "main.js").read_text(), "edited\n")
        self.run_ctx(self.install, force=True)
        self.assertEqual((self.live / "main.js").read_text(), "two\n")

    def test_refuses_unowned_file_but_adopts_identical_one(self):
        self.ship("main.js", "one\n")
        self.ship("other.js", "x\n")
        self.live.mkdir(parents=True)
        (self.live / "main.js").write_text("someone else's\n")
        (self.live / "other.js").write_text("x\n")
        out = self.run_ctx(self.install)
        self.assertIn("wasn't installed by grimoire", out)
        self.assertEqual((self.live / "main.js").read_text(), "someone else's\n")
        self.assertNotIn("t/m/main.js", self.manifest())
        self.assertEqual(self.manifest().get("t/m/other.js").kind, "install")

    def test_refuses_to_write_through_a_symlink(self):
        self.ship("main.js", "one\n")
        elsewhere = self.home / "elsewhere.js"
        elsewhere.write_text("theirs\n")
        self.live.mkdir(parents=True)
        (self.live / "main.js").symlink_to(elsewhere)
        out = self.run_ctx(self.install, force=True)
        self.assertIn("is a symlink", out)
        self.assertEqual(elsewhere.read_text(), "theirs\n")

    def test_missing_folder_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            self.run_ctx(self.install)

    def test_dry_run_touches_nothing(self):
        self.ship("main.js", "one\n")
        out = self.run_ctx(self.install, dry_run=True)
        self.assertIn(f"[dry-run] install t/m/main.js -> {self.live / 'main.js'}", out)
        self.assertFalse(self.live.exists())
        self.assertEqual(len(self.manifest()), 0)

    def test_accept_pulls_live_edits_back_and_resets_baseline(self):
        src = self.ship("main.js", "one\n")
        self.ship("same.js", "s\n")
        self.run_ctx(self.install)
        (self.live / "main.js").write_text("edited\n")
        (self.live / "new.js").write_text("not shipped\n")
        out = self.run_ctx(self.install, accepting=True)
        self.assertIn("accepted t/m/main.js", out)
        self.assertIn("t/m/same.js: not modified", out)
        self.assertEqual(src.read_text(), "edited\n")
        self.assertFalse((self.rite_dir / "m" / "new.js").exists())
        self.assertEqual(self.run_ctx(self.install), "", "accepted edit is clean")

    def test_accept_refuses_secrets(self):
        src = self.ship("main.js", "one\n")
        self.run_ctx(self.install)
        (self.live / "main.js").write_text("aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n")
        with self.assertRaises(SystemExit):
            self.run_ctx(self.install, accepting=True)
        self.assertEqual(src.read_text(), "one\n")


class Registration(Root):
    def test_registered_keys_cover_only_file_producing_ops(self):
        ctx = RiteContext("work", self.root, "t")
        ctx.copy("a", "b")
        ctx.write("g", "x")
        ctx.patch("p.json", str(self.home / "p.json"))
        ctx.install("m", str(self.home / "m"))
        (self.rite_dir / "m" / "sub").mkdir(parents=True)
        (self.rite_dir / "m" / "sub" / "x.js").write_text("x")
        ctx.link("a", str(self.home / "a"))
        ctx.hook("noop", lambda: None)
        ctx.doc(lambda **_: None)
        self.assertEqual(
            ctx.registered_keys(), {"t/a", "t/b", "t/g", "t/p.json", "t/m/sub/x.js"}
        )


if __name__ == "__main__":
    unittest.main()
