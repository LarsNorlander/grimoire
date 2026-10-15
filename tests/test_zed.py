"""Zed's actual rite output under work and personal profiles."""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from arcana.manifest import Manifest
from arcana.rites import load_rite
from arcana.tome import LinkOp

REPO = Path(__file__).resolve().parents[1]


class ProfileSettings(unittest.TestCase):
    def test_cast_keeps_claude_on_work_only_across_profile_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            rite_dir = root / "rites" / "zed"
            shutil.copytree(REPO / "rites" / "zed", rite_dir)
            target = Path(tmp) / "home" / "settings.json"
            shared = json.loads((rite_dir / "settings.json").read_text())
            for profile in ("personal", "work", "personal"):
                with self.subTest(profile=profile):
                    ctx = load_rite(rite_dir / "rite.py", profile, root)
                    for op in ctx._ops:
                        if isinstance(op, LinkOp):
                            op.target = str(target)
                    with redirect_stdout(io.StringIO()):
                        ctx.execute()
                    settings = json.loads(target.read_text())
                    self.assertTrue(target.is_symlink())
                    self.assertEqual(
                        target.readlink(), root / "tome" / "zed" / "settings.json"
                    )
                    if profile == "work":
                        self.assertEqual(
                            settings.pop("agent_servers")["claude-acp"],
                            {"type": "registry"},
                        )
                    else:
                        self.assertNotIn(
                            "claude-acp", settings.get("agent_servers", {})
                        )
                    self.assertEqual(settings, shared)
                    entry = Manifest.load(root / "tome").get("zed/settings.json")
                    self.assertIsNotNone(entry)
                    assert entry is not None
                    self.assertEqual(entry.kind, "write")
