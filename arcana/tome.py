"""Build context for grimoire rite build scripts."""

import shutil
import sys
from pathlib import Path


class BuildContext:
    def __init__(self, profile: str, grimoire_root: Path, tool: str):
        self.profile = profile
        self.grimoire_root = grimoire_root
        self.tool = tool
        self.rite_dir = grimoire_root / "rites" / tool
        self.tome_dir = grimoire_root / "tome" / tool

    @classmethod
    def from_args(cls) -> "BuildContext":
        profile = sys.argv[1]
        grimoire_root = Path(sys.argv[2])
        tool = Path(sys.argv[0]).resolve().parent.name
        return cls(profile, grimoire_root, tool)

    def copy(self, *files: str) -> None:
        self.tome_dir.mkdir(parents=True, exist_ok=True)
        for filename in files:
            shutil.copy2(self.rite_dir / filename, self.tome_dir / filename)
            print(f"  built tome/{self.tool}/{filename}")
