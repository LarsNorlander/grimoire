"""Context for grimoire rite scripts (build and accept modes)."""

import hashlib
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from detect_secrets.core.secrets_collection import SecretsCollection
from detect_secrets.settings import default_settings

from arcana import patch as patch_mod
from arcana.docs import DocPage
from arcana.manifest import Manifest

_PROFILE_DIRECTIVE_RE = re.compile(r"#\s*profile:\s*(.+?)\s*$", re.IGNORECASE)


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
    except OSError, UnicodeDecodeError:
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
    """Imperative setup, run on cast.

    `unless` is the idempotency guard: when it returns true the hook is
    skipped, and dry run can say so instead of only naming the hook.
    """

    name: str
    fn: Callable
    unless: Callable[[], bool] | None = None


@dataclass
class PatchOp:
    """Own a set of keys inside a JSON file the machine otherwise owns.

    `filename` is a fragment in the rite dir; its leaf keys are the owned
    set. `target` is the live file, written in place — the one op that
    doesn't symlink, because the rest of the file isn't ours to move.
    """

    filename: str
    target: str


@dataclass
class DocOp:
    """Documentation content a rite offers about itself.

    Inert during cast/accept — `execute()` never touches it, so generating
    docs can't move a symlink or rewrite a tome file. Only `grimoire scribe`
    reads these, via `registered_docs()`.
    """

    page: DocPage | Callable


class RiteSkipped(Exception):
    """Raised in-process when a rite is skipped due to profile requirements."""


class RiteContext:
    def __init__(
        self,
        profile: str,
        grimoire_root: Path,
        tool: str,
        force: bool = False,
        accepting: bool = False,
    ):
        self.profile = profile
        self.grimoire_root = grimoire_root
        self.tool = tool
        self.force = force
        self.accepting = accepting
        self.rite_dir = grimoire_root / "rites" / tool
        self.tome_dir = grimoire_root / "tome" / tool
        self._tome_root = grimoire_root / "tome"
        self._manifest = Manifest.load(self._tome_root)
        self._dirty = False
        self._ops: list[CopyOp | WriteOp | LinkOp | HookOp | PatchOp | DocOp] = []

    def _manifest_key(self, filename: str) -> str:
        return f"{self.tool}/{filename}"

    def _is_externally_modified(self, filename: str) -> bool:
        dest = self.tome_dir / filename
        if not dest.exists():
            return False
        baseline = self._manifest.hash(self._manifest_key(filename))
        return baseline is not None and _hash_file(dest) != baseline

    def _update_manifest(
        self, filename: str, kind: str, digest: str | None = None
    ) -> None:
        key = self._manifest_key(filename)
        self._manifest.record(key, digest or _hash_file(self.tome_dir / filename), kind)
        self._dirty = True

    def _record_links(self) -> None:
        """Write this pass's link destinations into the manifest.

        The list is replaced, not appended, so a rite that stops linking a
        file leaves no stale destination behind for GC to act on.
        """
        by_file: dict[str, list[str]] = {}
        for op in self._ops:
            if isinstance(op, LinkOp):
                by_file.setdefault(op.filename, []).append(
                    str(Path(op.target).expanduser())
                )
        for key in self.registered_keys():
            entry = self._manifest.get(key)
            if entry is None:
                continue
            links = sorted(set(by_file.get(key.split("/", 1)[1], [])))
            if entry.links != links:
                self._manifest.set_links(key, links)
                self._dirty = True

    def _save_if_dirty(self) -> None:
        if self._dirty:
            self._manifest.save()

    # --- Public API: operation builders ---

    def copy(self, *files: str) -> None:
        self._ops.append(CopyOp(files))

    def write(self, filename: str, content: str | Callable) -> None:
        self._ops.append(WriteOp(filename, content))

    def link(self, filename: str, target: str) -> None:
        self._ops.append(LinkOp(filename, target))

    def hook(
        self, name: str, fn: Callable, *, unless: Callable[[], bool] | None = None
    ) -> None:
        """Register imperative setup. `unless()` true means already done: skip."""
        self._ops.append(HookOp(name, fn, unless))

    def patch(self, filename: str, target: str) -> None:
        """Own the keys of JSON fragment `filename` inside the live file `target`.

        Cast merges the fragment into the target and prunes keys the fragment
        used to own. Accept pulls the owned keys back into the fragment.
        Drift is judged on the owned keys only; the rest of the file is free
        to change.
        """
        self._ops.append(PatchOp(filename, target))

    def doc(self, page: DocPage | Callable) -> None:
        """Register a cheatsheet page for this tool.

        Takes a `DocPage` or a builder called with the same kwargs as
        `write()`'s (`profile`, `rite_dir`, `grimoire_root`). Prefer a builder:
        it defers parsing until `grimoire scribe` actually asks, so `cast` pays
        nothing for docs it isn't generating.
        """
        self._ops.append(DocOp(page))

    # --- Introspection ---

    def registered_keys(self) -> set[str]:
        """Manifest keys ({tool}/{filename}) registered via copy()/write()/patch()."""
        keys: set[str] = set()
        for op in self._ops:
            if isinstance(op, CopyOp):
                for f in op.files:
                    keys.add(self._manifest_key(f))
            elif isinstance(op, (WriteOp, PatchOp)):
                keys.add(self._manifest_key(op.filename))
        return keys

    def registered_docs(self) -> list[DocPage]:
        """Resolve every registered DocOp into a DocPage.

        Calls builders — so this is where doc-time parsing happens. Read-only
        with respect to tome/ and the filesystem.
        """
        pages: list[DocPage] = []
        for op in self._ops:
            if not isinstance(op, DocOp):
                continue
            page = op.page
            if callable(page):
                page = page(
                    profile=self.profile,
                    rite_dir=self.rite_dir,
                    grimoire_root=self.grimoire_root,
                )
            pages.append(page)
        return pages

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
                    self._exec_hook(op, dry_run=dry_run)
            elif isinstance(op, PatchOp):
                if self.accepting:
                    self._exec_patch_accept(op.filename, op.target, dry_run=dry_run)
                else:
                    self._exec_patch(op.filename, op.target, dry_run=dry_run)
        if not self.accepting and not dry_run:
            self._record_links()
        self._save_if_dirty()

    def _exec_copy(self, *files: str, dry_run: bool = False) -> None:
        if dry_run:
            for filename in files:
                print(
                    f"  [dry-run] copy {self.tool}/{filename}"
                    f" → tome/{self.tool}/{filename}"
                )
            return
        self.tome_dir.mkdir(parents=True, exist_ok=True)
        for filename in files:
            if not self.force and self._is_externally_modified(filename):
                print(
                    f"  SKIPPED tome/{self.tool}/{filename}"
                    f" — externally modified (use --force to overwrite)"
                )
                continue
            shutil.copy2(self.rite_dir / filename, self.tome_dir / filename)
            self._update_manifest(filename, "copy")
            print(f"  built tome/{self.tool}/{filename}")

    def _exec_write(
        self, filename: str, content: str | Callable, dry_run: bool = False
    ) -> None:
        if self.accepting:
            print(
                f"  WARNING {self.tool}/{filename}"
                f" — generated file, needs manual reconciliation"
            )
            return
        if dry_run:
            print(f"  [dry-run] write tome/{self.tool}/{filename}")
            return
        text: str = (
            content(
                profile=self.profile,
                rite_dir=self.rite_dir,
                grimoire_root=self.grimoire_root,
            )
            if callable(content)
            else content
        )
        self.tome_dir.mkdir(parents=True, exist_ok=True)
        if not self.force and self._is_externally_modified(filename):
            print(
                f"  SKIPPED tome/{self.tool}/{filename}"
                f" — externally modified (use --force to overwrite)"
            )
            return
        (self.tome_dir / filename).write_text(text)
        self._update_manifest(filename, "write")
        print(f"  built tome/{self.tool}/{filename}")

    def _exec_accept(self, *files: str, dry_run: bool = False) -> None:
        for filename in files:
            if not self._is_externally_modified(filename):
                print(f"  {self.tool}/{filename}: not modified — skipping")
                continue
            rite_file = self.rite_dir / filename
            if not rite_file.exists():
                print(
                    f"  {self.tool}/{filename}: no matching source"
                    f" — needs manual reconciliation"
                )
                continue
            tome_file = self.tome_dir / filename
            if dry_run:
                print(
                    f"  [dry-run] accept {self.tool}/{filename}"
                    f" → rites/{self.tool}/{filename}"
                )
                continue
            if secrets := _scan_for_secrets(tome_file):
                print(
                    f"  ERROR {self.tool}/{filename}: potential secrets detected"
                    f" — refusing to accept"
                )
                for s in secrets:
                    print(f"    line {s['line_number']}: {s['type']}")
                sys.exit(1)
            shutil.copy2(tome_file, rite_file)
            self._update_manifest(filename, "copy")
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

    def _exec_hook(self, op: HookOp, dry_run: bool = False) -> None:
        done = bool(op.unless()) if op.unless else False
        if dry_run:
            state = "already done, would skip" if done else "would run"
            print(f"  [dry-run] hook: {op.name} — {state}")
            return
        if done:
            return
        op.fn()

    # --- patch(): key-level ownership inside a live JSON file ---

    def _owned_paths(self, filename: str) -> list[patch_mod.KeyPath]:
        """Paths grimoire applied on the last cast — the tome fragment.

        Drift and accept judge against what was *applied*, not what the
        source declares now: a key added to the source but not yet cast
        must not read as external modification of the target.
        """
        tome_file = self.tome_dir / filename
        if tome_file.exists():
            return patch_mod.leaves(patch_mod.load(tome_file))
        return []

    def _live_fragment(self, filename: str, doc: dict) -> dict:
        return patch_mod.extract(doc, self._owned_paths(filename))[0]

    def _patch_externally_modified(self, filename: str, doc: dict) -> bool:
        baseline = self._manifest.hash(self._manifest_key(filename))
        if baseline is None or not (self.tome_dir / filename).exists():
            return False
        live = patch_mod.canonical(self._live_fragment(filename, doc))
        return hashlib.sha256(live).hexdigest() != baseline

    def _exec_patch(self, filename: str, target: str, dry_run: bool = False) -> None:
        source = self.rite_dir / filename
        dest = Path(target).expanduser()
        tome_file = self.tome_dir / filename
        if dry_run:
            print(f"  [dry-run] patch {self.tool}/{filename} -> {dest}")
            return
        try:
            fragment = patch_mod.load(source)
            doc = patch_mod.load(dest) if dest.exists() else {}
        except ValueError as e:
            print(f"  ERROR {self.tool}/{filename}: {e} — skipping")
            return
        if (
            dest.exists()
            and not self.force
            and self._patch_externally_modified(filename, doc)
        ):
            print(
                f"  SKIPPED {dest}"
                f" — owned keys externally modified (use --force to overwrite)"
            )
            return
        new_paths = patch_mod.leaves(fragment)
        stale = [p for p in self._owned_paths(filename) if p not in new_paths]
        doc = patch_mod.merge(patch_mod.prune(doc, stale), fragment)
        dest.parent.mkdir(parents=True, exist_ok=True)
        patch_mod.dump(dest, doc)
        self.tome_dir.mkdir(parents=True, exist_ok=True)
        tome_file.write_bytes(patch_mod.canonical(fragment))
        self._update_manifest(filename, "patch")
        self._manifest.set_target(self._manifest_key(filename), str(dest))
        pruned = f", pruned {len(stale)}" if stale else ""
        print(f"  patched {dest} ({len(new_paths)} keys{pruned})")

    def _exec_patch_accept(
        self, filename: str, target: str, dry_run: bool = False
    ) -> None:
        source = self.rite_dir / filename
        dest = Path(target).expanduser()
        if not dest.exists():
            print(f"  {self.tool}/{filename}: target {dest} missing — skipping")
            return
        if not source.exists():
            print(
                f"  {self.tool}/{filename}: no matching source"
                f" — needs manual reconciliation"
            )
            return
        try:
            doc = patch_mod.load(dest)
            fragment = patch_mod.load(source)
        except ValueError as e:
            print(f"  ERROR {self.tool}/{filename}: {e} — skipping")
            return
        if not self._patch_externally_modified(filename, doc):
            print(f"  {self.tool}/{filename}: not modified — skipping")
            return
        if dry_run:
            print(f"  [dry-run] accept {dest} -> rites/{self.tool}/{filename}")
            return
        live, missing = patch_mod.extract(doc, self._owned_paths(filename))
        for path in missing:
            print(
                f"  WARNING {self.tool}/{filename}: {'.'.join(path)}"
                f" missing from target — keeping source value"
            )
        merged = patch_mod.merge(fragment, live)
        # Scan before touching the source, on the bytes we'd write.
        staging = self.tome_dir / f".{filename}.accept"
        staging.write_bytes(patch_mod.canonical(merged))
        try:
            if secrets := _scan_for_secrets(staging):
                print(
                    f"  ERROR {self.tool}/{filename}: potential secrets detected"
                    f" — refusing to accept"
                )
                for s in secrets:
                    print(f"    line {s['line_number']}: {s['type']}")
                sys.exit(1)
        finally:
            staging.unlink(missing_ok=True)
        patch_mod.dump(source, merged)
        # The tome fragment remembers the owned paths; the manifest records
        # what the target actually holds, so a kept-but-missing key reads as
        # a pending cast rather than as drift.
        (self.tome_dir / filename).write_bytes(patch_mod.canonical(merged))
        live_digest = hashlib.sha256(patch_mod.canonical(live)).hexdigest()
        self._update_manifest(filename, "patch", live_digest)
        self._manifest.set_target(self._manifest_key(filename), str(dest))
        print(f"  accepted {self.tool}/{filename}")
