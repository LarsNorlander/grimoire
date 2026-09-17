"""Key-level ownership inside a config file the machine otherwise owns.

A `patch()` rite declares a *fragment*: a partial JSON document whose leaf
keys grimoire owns. Everything else in the target file belongs to the
machine (or to the tool that rewrites its own config). These helpers are
pure functions over plain dicts; `RiteContext` does the file I/O.

Ownership is structural: dict values are traversed, anything else (arrays,
scalars) is a leaf and is replaced whole. Arrays are not unioned — a union
can't be pulled back on accept, and removals would never propagate.
"""

import json
from pathlib import Path
from typing import Any

KeyPath = tuple[str, ...]


def leaves(fragment: dict, prefix: KeyPath = ()) -> list[KeyPath]:
    """Every owned key path in a fragment, depth-first, in source order."""
    out: list[KeyPath] = []
    for key, value in fragment.items():
        path = (*prefix, key)
        if isinstance(value, dict) and value:
            out.extend(leaves(value, path))
        else:
            out.append(path)
    return out


def extract(doc: dict, paths: list[KeyPath]) -> tuple[dict, list[KeyPath]]:
    """Pull the owned paths out of a document.

    Returns (fragment, missing): the fragment holds every path that was
    present, nested the same way; `missing` lists paths the document lacks.
    """
    fragment: dict = {}
    missing: list[KeyPath] = []
    for path in paths:
        node: Any = doc
        for key in path:
            if not isinstance(node, dict) or key not in node:
                missing.append(path)
                break
            node = node[key]
        else:
            _set(fragment, path, node)
    return fragment, missing


def merge(doc: dict, fragment: dict) -> dict:
    """Return a copy of `doc` with every leaf of `fragment` written in."""
    out = dict(doc)
    for key, value in fragment.items():
        if isinstance(value, dict) and value and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def prune(doc: dict, paths: list[KeyPath]) -> dict:
    """Return a copy of `doc` without the given paths.

    A parent dict left empty by a removal is dropped too: if nothing of the
    machine's remains under it, it was ours.
    """
    out = dict(doc)
    for path in paths:
        _delete(out, path)
    return out


def canonical(fragment: dict) -> bytes:
    """Stable bytes for hashing and diffing: sorted keys, two-space indent."""
    return (
        json.dumps(fragment, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()


def load(path: Path) -> dict:
    """Parse a JSON object from disk. Raises ValueError with the path on failure."""
    try:
        doc = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(
            f"{path}: not valid JSON ({e.msg} at line {e.lineno})"
        ) from None
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: top level must be a JSON object")
    return doc


def dump(path: Path, doc: dict) -> None:
    """Write a document the way most tools format their own config."""
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def _set(doc: dict, path: KeyPath, value: Any) -> None:
    node = doc
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def _delete(doc: dict, path: KeyPath) -> None:
    parents: list[tuple[dict, str]] = []
    node: Any = doc
    for key in path[:-1]:
        if not isinstance(node, dict) or key not in node:
            return
        parents.append((node, key))
        node[key] = dict(node[key]) if isinstance(node[key], dict) else node[key]
        node = node[key]
    if not isinstance(node, dict) or path[-1] not in node:
        return
    del node[path[-1]]
    for parent, key in reversed(parents):
        if parent[key] == {}:
            del parent[key]
        else:
            break
