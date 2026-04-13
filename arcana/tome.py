"""Context for grimoire rite scripts (build and accept modes)."""

import hashlib
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, ClassVar

from detect_secrets import SecretsCollection
from detect_secrets.settings import default_settings

MANIFEST_FILENAME = ".manifest"

_PROFILE_DIRECTIVE_RE = re.compile(r'#\s*profile:\s*(.+?)\s*$', re.IGNORECASE)


def parse_rite_profiles(rite_path: Path) -> set[str] | None:
    """Parse `# profile: <names>` from a rite's header comment.

    Returns the set of profiles the rite is declared compatible with, or
    None if no directive is present (rite applies to every profile).

    Scans only the contiguous comment block at the top of the file — stops
    at the first non-comment, non-blank line. The directive key is matched
    case-insensitively; values are taken as written (profile names match
    `VALID_PROFILES` exactly). Trailing `#` comments on the directive line
    are stripped before splitting (e.g., `# profile: work  # TODO` yields
    just `{'work'}`).

    Profile gating is metadata, not code, so this is the single source of
    truth that both `_load_rite` and shell-completion consult.
    """
    try:
        text = rite_path.read_text()
    except (OSError, UnicodeDecodeError):
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#!"):
            continue
        if not line.startswith("#"):
            return None  # reached code without a directive
        if m := _PROFILE_DIRECTIVE_RE.match(line):
            value = m.group(1)
            if "#" in value:
                value = value.split("#", 1)[0]
            profiles = value.split()
            return set(profiles) if profiles else None
    return None


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _scan_for_secrets(path: Path) -> list[dict]:
    """Return list of detected secrets (type + line_number) in a file."""
    with default_settings():
        collection = SecretsCollection()
        collection.scan_file(str(path))
    found = []
    for _, secret_set in collection.data.items():
        for secret in secret_set:
            found.append({"type": secret.type, "line_number": secret.line_number})
    return found


def load_manifest(tome_root: Path) -> dict[str, str]:
    manifest_path = tome_root / MANIFEST_FILENAME
    if not manifest_path.exists():
        return {}
    entries = {}
    for line in manifest_path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            entries[key] = value
    return entries


def save_manifest(tome_root: Path, entries: dict[str, str]) -> None:
    manifest_path = tome_root / MANIFEST_FILENAME
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in sorted(entries.items())]
    manifest_path.write_text("\n".join(lines) + "\n")


@dataclass
class CopyOp:
    files: tuple[str, ...]


@dataclass
class WriteOp:
    filename: str
    content: str | Callable


@dataclass
class LinkOp:
    filename: str
    target: str


@dataclass
class HookOp:
    name: str
    fn: Callable


class RiteSkipped(Exception):
    """Raised in-process when a rite is skipped due to profile requirements."""


class RiteContext:
    _current: ClassVar["RiteContext | None"] = None

    def __init__(self, profile: str, grimoire_root: Path, tool: str,
                 force: bool = False, accepting: bool = False):
        self.profile = profile
        self.grimoire_root = grimoire_root
        self.tool = tool
        self.force = force
        self.accepting = accepting
        self.rite_dir = grimoire_root / "rites" / tool
        self.tome_dir = grimoire_root / "tome" / tool
        self._tome_root = grimoire_root / "tome"
        self._manifest = load_manifest(self._tome_root)
        self._dirty = False
        self._ops: list[CopyOp | WriteOp | LinkOp | HookOp] = []

    @classmethod
    def from_args(cls) -> "RiteContext":
        """Return the context a rite should register operations against.

        Two modes:

        - **CLI dispatch** (the common case): the CLI pre-populates `_current`
          via `_load_rite` before importing the rite module. We return that.
        - **Standalone invocation** (for debugging a single rite without the
          CLI): `./rites/<tool>/rite <profile> <grimoire_root> [--force] [--accept]`.
          Parse argv, honor any `# profile:` frontmatter, build a fresh
          context, and register `execute()` via atexit so the rite's
          declarative ops run at process exit.
        """
        if cls._current is not None:
            return cls._current
        import atexit
        profile = sys.argv[1]
        grimoire_root = Path(sys.argv[2])
        force = "--force" in sys.argv[3:]
        accepting = "--accept" in sys.argv[3:]
        rite_path = Path(sys.argv[0]).resolve()
        tool = rite_path.parent.name
        if not accepting:
            allowed = parse_rite_profiles(rite_path)
            if allowed and profile not in allowed:
                print(f"  skipped {tool} — requires {'/'.join(sorted(allowed))} profile")
                sys.exit(0)
        ctx = cls(profile, grimoire_root, tool, force=force, accepting=accepting)
        atexit.register(ctx.execute)
        return ctx

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
        self._dirty = True

    def _save_if_dirty(self) -> None:
        if self._dirty:
            save_manifest(self._tome_root, self._manifest)

    # --- Public API: operation builders ---

    def copy(self, *files: str) -> None:
        self._ops.append(CopyOp(files))

    def write(self, filename: str, content: str | Callable) -> None:
        self._ops.append(WriteOp(filename, content))

    def link(self, filename: str, target: str) -> None:
        self._ops.append(LinkOp(filename, target))

    def hook(self, name: str, fn: Callable) -> None:
        self._ops.append(HookOp(name, fn))

    # --- Introspection ---

    def registered_keys(self) -> set[str]:
        """Manifest keys ({tool}/{filename}) this context has registered via copy()/write()."""
        keys: set[str] = set()
        for op in self._ops:
            if isinstance(op, CopyOp):
                for f in op.files:
                    keys.add(self._manifest_key(f))
            elif isinstance(op, WriteOp):
                keys.add(self._manifest_key(op.filename))
        return keys

    # --- Execution ---

    def execute(self, dry_run: bool = False) -> None:
        for op in self._ops:
            if isinstance(op, CopyOp):
                if self.accepting:
                    self._exec_accept(*op.files, dry_run=dry_run)
                else:
                    self._exec_copy(*op.files, dry_run=dry_run)
            elif isinstance(op, WriteOp):
                self._exec_write(op.filename, op.content, dry_run=dry_run)
            elif isinstance(op, LinkOp):
                if not self.accepting:
                    self._exec_link(op.filename, op.target, dry_run=dry_run)
            elif isinstance(op, HookOp):
                if not self.accepting:
                    self._exec_hook(op.name, op.fn, dry_run=dry_run)
        self._save_if_dirty()

    def _exec_copy(self, *files: str, dry_run: bool = False) -> None:
        if dry_run:
            for filename in files:
                print(f"  [dry-run] copy {self.tool}/{filename} → tome/{self.tool}/{filename}")
            return
        self.tome_dir.mkdir(parents=True, exist_ok=True)
        for filename in files:
            if not self.force and self._is_externally_modified(filename):
                print(f"  SKIPPED tome/{self.tool}/{filename} — externally modified (use --force to overwrite)")
                continue
            shutil.copy2(self.rite_dir / filename, self.tome_dir / filename)
            self._update_manifest(filename)
            print(f"  built tome/{self.tool}/{filename}")

    def _exec_write(self, filename: str, content: str | Callable, dry_run: bool = False) -> None:
        if self.accepting:
            print(f"  WARNING {self.tool}/{filename} — generated file, needs manual reconciliation")
            return
        if dry_run:
            print(f"  [dry-run] write tome/{self.tool}/{filename}")
            return
        if callable(content):
            content = content(profile=self.profile, rite_dir=self.rite_dir, grimoire_root=self.grimoire_root)
        self.tome_dir.mkdir(parents=True, exist_ok=True)
        if not self.force and self._is_externally_modified(filename):
            print(f"  SKIPPED tome/{self.tool}/{filename} — externally modified (use --force to overwrite)")
            return
        (self.tome_dir / filename).write_text(content)
        self._update_manifest(filename)
        print(f"  built tome/{self.tool}/{filename}")

    def _exec_accept(self, *files: str, dry_run: bool = False) -> None:
        for filename in files:
            if not self._is_externally_modified(filename):
                print(f"  {self.tool}/{filename}: not modified — skipping")
                continue
            rite_file = self.rite_dir / filename
            if not rite_file.exists():
                print(f"  {self.tool}/{filename}: no matching source — needs manual reconciliation")
                continue
            tome_file = self.tome_dir / filename
            if dry_run:
                print(f"  [dry-run] accept {self.tool}/{filename} → rites/{self.tool}/{filename}")
                continue
            if secrets := _scan_for_secrets(tome_file):
                print(f"  ERROR {self.tool}/{filename}: potential secrets detected — refusing to accept")
                for s in secrets:
                    print(f"    line {s['line_number']}: {s['type']}")
                sys.exit(1)
            shutil.copy2(tome_file, rite_file)
            self._update_manifest(filename)
            print(f"  accepted {self.tool}/{filename}")

    def _exec_link(self, filename: str, target: str, dry_run: bool = False) -> None:
        source = self.tome_dir / filename
        dest = Path(target).expanduser()
        if dry_run:
            print(f"  [dry-run] link {dest} -> {source}")
            return
        # No-op if the symlink is already pointing where we'd aim it.
        # (Keeps repeat-cast output quiet when nothing has moved.)
        if dest.is_symlink() and dest.readlink() == source:
            return
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

    def _exec_hook(self, name: str, fn: Callable, dry_run: bool = False) -> None:
        if dry_run:
            print(f"  [dry-run] hook: {name}")
            return
        fn()
