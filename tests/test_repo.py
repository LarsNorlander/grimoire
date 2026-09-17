"""Tests for `grimoire update`: a bare remote, a clone, and every outcome.

Run with: uv run python -m unittest
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

from arcana import repo
from arcana.repo import Outcome


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


class Remote(unittest.TestCase):
    """`origin` is a bare repo; `clone` is the checkout under test; `other`
    is a second clone used to publish upstream commits."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.origin = base / "origin.git"
        git(base, "init", "--bare", "-q", "-b", "main", str(self.origin))
        self.other = base / "other"
        git(base, "clone", "-q", str(self.origin), str(self.other))
        self.identity(self.other)
        (self.other / "README").write_text("v1\n")
        git(self.other, "add", "README")
        git(self.other, "commit", "-q", "-m", "chore: Initial")
        git(self.other, "push", "-q", "-u", "origin", "main")
        self.clone = base / "clone"
        git(base, "clone", "-q", str(self.origin), str(self.clone))
        self.identity(self.clone)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def identity(cwd: Path):
        git(cwd, "config", "user.email", "t@example.com")
        git(cwd, "config", "user.name", "Test")

    def publish(self, path: str, text: str, message: str) -> None:
        (self.other / path).parent.mkdir(parents=True, exist_ok=True)
        (self.other / path).write_text(text)
        git(self.other, "add", path)
        git(self.other, "commit", "-q", "-m", message)
        git(self.other, "push", "-q", "origin", "main")

    def local_commit(self, path: str, text: str, message: str) -> None:
        (self.clone / path).write_text(text)
        git(self.clone, "add", path)
        git(self.clone, "commit", "-q", "-m", message)


class Outcomes(Remote):
    def test_up_to_date(self):
        u = repo.update(self.clone)
        self.assertEqual(u.outcome, Outcome.UP_TO_DATE)
        self.assertEqual(u.old_head, u.new_head)

    def test_fast_forward_reports_incoming_and_suggests_verbs(self):
        self.publish("runes/work.nix", "x\n", "feat(runes): Add x")
        self.publish("rites/zsh/zshrc", "y\n", "fix(zsh): y")
        before = git(self.clone, "rev-parse", "HEAD")
        u = repo.update(self.clone)
        self.assertEqual(u.outcome, Outcome.FAST_FORWARDED)
        self.assertEqual(u.old_head, before)
        self.assertEqual(u.new_head, git(self.clone, "rev-parse", "HEAD"))
        self.assertEqual(
            [m.split(" ", 1)[1] for m in u.incoming],
            ["feat(runes): Add x", "fix(zsh): y"],
        )
        self.assertEqual(sorted(u.changed_paths), ["rites/zsh/zshrc", "runes/work.nix"])
        self.assertEqual(u.suggests(), ["inscribe", "cast"])
        self.assertEqual((self.clone / "rites/zsh/zshrc").read_text(), "y\n")

    def test_suggests_nothing_for_docs_only_changes(self):
        self.publish("README", "v2\n", "docs: Update")
        self.assertEqual(repo.update(self.clone).suggests(), [])

    def test_dirty_tree_refuses_before_fetching(self):
        (self.clone / "README").write_text("edited\n")
        self.publish("README", "v2\n", "docs: Update")
        u = repo.update(self.clone)
        self.assertEqual(u.outcome, Outcome.DIRTY)
        self.assertEqual(u.dirty_files, [" M README"])
        # Nothing was fetched or merged.
        self.assertEqual((self.clone / "README").read_text(), "edited\n")
        self.assertEqual(
            git(self.clone, "rev-parse", "origin/main"),
            git(self.clone, "rev-parse", "HEAD"),
        )

    def test_diverged_names_local_commits_and_touches_nothing(self):
        self.local_commit("README", "local\n", "chore: Local work")
        self.publish("other", "z\n", "chore: Upstream work")
        head = git(self.clone, "rev-parse", "HEAD")
        u = repo.update(self.clone)
        self.assertEqual(u.outcome, Outcome.DIVERGED)
        self.assertEqual(
            [m.split(" ", 1)[1] for m in u.local_only], ["chore: Local work"]
        )
        self.assertEqual(git(self.clone, "rev-parse", "HEAD"), head)

    def test_ahead_only_is_not_a_conflict(self):
        self.local_commit("README", "local\n", "chore: Unpushed")
        u = repo.update(self.clone)
        self.assertEqual(u.outcome, Outcome.AHEAD)
        self.assertEqual(
            [m.split(" ", 1)[1] for m in u.local_only], ["chore: Unpushed"]
        )
        self.assertEqual(u.old_head, u.new_head)

    def test_no_upstream(self):
        git(self.clone, "checkout", "-q", "-b", "feature")
        u = repo.update(self.clone)
        self.assertEqual(u.outcome, Outcome.NO_UPSTREAM)
        self.assertTrue(u.error)

    def test_fetch_failure_is_reported(self):
        git(
            self.clone,
            "remote",
            "set-url",
            "origin",
            str(Path(self.tmp.name, "missing.git")),
        )
        u = repo.update(self.clone)
        self.assertEqual(u.outcome, Outcome.FETCH_FAILED)
        self.assertTrue(u.error)


if __name__ == "__main__":
    unittest.main()
