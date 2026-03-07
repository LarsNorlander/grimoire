"""Build context for grimoire rite build scripts."""

import atexit
import hashlib
import shutil
import sys
from pathlib import Path

MANIFEST_FILENAME = ".manifest"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(tome_root: Path) -> dict[str, str]:
    manifest_path = tome_root / MANIFEST_FILENAME
    if not manifest_path.exists():
        return {}
    entries = {}
    for line in manifest_path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            entries[key] = value
    return entries


def _save_manifest(tome_root: Path, entries: dict[str, str]) -> None:
    manifest_path = tome_root / MANIFEST_FILENAME
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in sorted(entries.items())]
    manifest_path.write_text("\n".join(lines) + "\n")


class BuildContext:
    def __init__(self, profile: str, grimoire_root: Path, tool: str, force: bool = False):
        self.profile = profile
        self.grimoire_root = grimoire_root
        self.tool = tool
        self.force = force
        self.rite_dir = grimoire_root / "rites" / tool
        self.tome_dir = grimoire_root / "tome" / tool
        self._tome_root = grimoire_root / "tome"
        self._manifest = _load_manifest(self._tome_root)
        self._dirty = False

    @classmethod
    def from_args(cls) -> "BuildContext":
        profile = sys.argv[1]
        grimoire_root = Path(sys.argv[2])
        force = len(sys.argv) > 3 and sys.argv[3] == "--force"
        tool = Path(sys.argv[0]).resolve().parent.name
        return cls(profile, grimoire_root, tool, force)

    def _manifest_key(self, filename: str) -> str:
        return f"{self.tool}/{filename}"

    def _is_externally_modified(self, filename: str) -> bool:
        dest = self.tome_dir / filename
        if not dest.exists():
            return False
        key = self._manifest_key(filename)
        if key not in self._manifest:
            return False
        return _hash_file(dest) != self._manifest[key]

    def _update_manifest(self, filename: str) -> None:
        key = self._manifest_key(filename)
        self._manifest[key] = _hash_file(self.tome_dir / filename)
        if not self._dirty:
            self._dirty = True
            atexit.register(_save_manifest, self._tome_root, self._manifest)

    def copy(self, *files: str) -> None:
        self.tome_dir.mkdir(parents=True, exist_ok=True)
        for filename in files:
            if not self.force and self._is_externally_modified(filename):
                print(f"  SKIPPED tome/{self.tool}/{filename} — externally modified (use --force to overwrite)")
                continue
            shutil.copy2(self.rite_dir / filename, self.tome_dir / filename)
            self._update_manifest(filename)
            print(f"  built tome/{self.tool}/{filename}")

    def write(self, filename: str, content: str) -> None:
        self.tome_dir.mkdir(parents=True, exist_ok=True)
        if not self.force and self._is_externally_modified(filename):
            print(f"  SKIPPED tome/{self.tool}/{filename} — externally modified (use --force to overwrite)")
            return
        (self.tome_dir / filename).write_text(content)
        self._update_manifest(filename)
        print(f"  built tome/{self.tool}/{filename}")

    def link(self, filename: str, target: str) -> None:
        source = self.tome_dir / filename
        dest = Path(target).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_symlink():
            dest.unlink()
            print(f"  updated {dest} -> {source}")
        elif dest.exists():
            print(f"  ERROR: {dest} already exists and is not a symlink — skipping")
            return
        else:
            print(f"  created {dest} -> {source}")
        dest.symlink_to(source)
