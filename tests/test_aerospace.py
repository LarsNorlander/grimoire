"""The aerospace rite's generated config: the service-mode `d` contract.

Run with: uv run python -m unittest
"""

import importlib.util
import unittest
from pathlib import Path

import tomlkit

REPO = Path(__file__).resolve().parents[1]
RITE_DIR = REPO / "rites" / "aerospace"


def _load():
    spec = importlib.util.spec_from_file_location(
        "aerospace_rite", RITE_DIR / "rite.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plain(text: str) -> dict:
    return tomlkit.parse(text).unwrap()


def _service_binding(text: str) -> dict:
    """The [mode.service.binding] table as plain Python."""
    return _plain(text)["mode"]["service"]["binding"]


class ServiceD(unittest.TestCase):
    def build(self, profile) -> dict:
        text = _load().build_aerospace(profile=profile, rite_dir=RITE_DIR)
        return _service_binding(text)

    def test_generated_file_carries_no_directives(self):
        for profile in ("work", "personal"):
            with self.subTest(profile=profile):
                text = _load().build_aerospace(profile=profile, rite_dir=RITE_DIR)
                self.assertNotIn("grimoire", _plain(text))
                self.assertNotRegex(text, r"(?m)^\[grimoire")

    def test_unknown_directive_fails_loudly(self):
        doc = tomlkit.parse(
            "[mode.service.binding]\n"
            'd = ["a"]\n'
            "[grimoire.service-d]\n"
            'exit = ["z"]\n'
            'typo = ["x"]\n'
        )
        with self.assertRaises(ValueError) as cm:
            _load().apply_directives(doc)
        self.assertIn("typo", str(cm.exception))

    def test_profile_entries_sit_between_body_and_exit_tail(self):
        base = _plain((RITE_DIR / "base.toml").read_text())
        body = base["mode"]["service"]["binding"]["d"]
        tail = base["grimoire"]["service-d"]["exit"]
        for profile in ("work", "personal"):
            with self.subTest(profile=profile):
                overlay = _plain((RITE_DIR / f"{profile}.toml").read_text())
                extra = overlay["grimoire"]["service-d"]["before-exit"]
                d = self.build(profile)["d"]
                self.assertEqual(d, body + extra + tail)
                self.assertEqual(d[-1], "mode main")


if __name__ == "__main__":
    unittest.main()
