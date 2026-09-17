"""The tome manifest: what grimoire last built, and where it put it.

One entry per managed file, keyed `tool/filename`:

- `hash`   — sha256 of the tome file as built (for patch(): of the owned
             keys as they stood in the target), the baseline drift is
             judged against.
- `kind`   — the op that produced it: copy, write, or patch.
- `links`  — symlinks a rite created to this tome file, so GC can remove
             them when the file is pruned instead of leaving them dangling.
- `target` — patch() only: the live file the fragment was merged into.

The file is JSON at `tome/.manifest`. The pre-v2 format was one `key=hash`
line per file; it is read transparently and rewritten as v2 on the next save.
Entries migrated that way carry a hash only until their rite is cast again.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

FILENAME = ".manifest"
VERSION = 2


@dataclass
class Entry:
    hash: str
    kind: str | None = None
    links: list[str] = field(default_factory=list)
    target: str | None = None

    def to_dict(self) -> dict:
        out: dict = {"hash": self.hash}
        if self.kind:
            out["kind"] = self.kind
        if self.links:
            out["links"] = sorted(self.links)
        if self.target:
            out["target"] = self.target
        return out

    @classmethod
    def from_dict(cls, d: dict) -> Entry:
        return cls(
            hash=d["hash"],
            kind=d.get("kind"),
            links=list(d.get("links", [])),
            target=d.get("target"),
        )


class Manifest:
    def __init__(self, path: Path, entries: dict[str, Entry] | None = None):
        self.path = path
        self._entries: dict[str, Entry] = entries or {}

    # -- persistence -----------------------------------------------------

    @classmethod
    def load(cls, tome_root: Path) -> Manifest:
        path = tome_root / FILENAME
        if not path.exists():
            return cls(path)
        text = path.read_text()
        if text.lstrip().startswith("{"):
            data = json.loads(text)
            entries = {k: Entry.from_dict(v) for k, v in data.get("files", {}).items()}
        else:
            entries = _parse_legacy(text)
        return cls(path, entries)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": VERSION,
            "files": {k: self._entries[k].to_dict() for k in sorted(self._entries)},
        }
        self.path.write_text(json.dumps(data, indent=2) + "\n")

    # -- reading ---------------------------------------------------------

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def __iter__(self):
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def keys(self) -> list[str]:
        return sorted(self._entries)

    def get(self, key: str) -> Entry | None:
        return self._entries.get(key)

    def hash(self, key: str) -> str | None:
        e = self._entries.get(key)
        return e.hash if e else None

    # -- writing ---------------------------------------------------------

    def record(self, key: str, digest: str, kind: str) -> Entry:
        """Set the baseline for a built file, keeping any recorded links/target."""
        e = self._entries.get(key)
        if e is None:
            e = self._entries[key] = Entry(hash=digest, kind=kind)
        else:
            e.hash, e.kind = digest, kind
        return e

    def set_links(self, key: str, links: list[str]) -> None:
        if key in self._entries:
            self._entries[key].links = sorted(set(links))

    def set_target(self, key: str, target: str) -> None:
        if key in self._entries:
            self._entries[key].target = target

    def remove(self, key: str) -> Entry | None:
        return self._entries.pop(key, None)


def _parse_legacy(text: str) -> dict[str, Entry]:
    entries: dict[str, Entry] = {}
    for line in text.splitlines():
        if "=" in line:
            key, digest = line.split("=", 1)
            entries[key] = Entry(hash=digest)
    return entries
