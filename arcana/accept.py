"""Accept externally modified tome files back into rite sources."""

import shutil
import sys
from pathlib import Path

from arcana.tome import _hash_file, _load_manifest, _save_manifest


def resolve_targets(manifest, targets):
    """Resolve target args to manifest keys. A target is a tool name or tool/filename."""
    keys = []
    for target in targets:
        if "/" in target:
            if target in manifest:
                keys.append(target)
            else:
                print(f"  no manifest entry for {target}")
        else:
            matched = [k for k in manifest if k.startswith(target + "/")]
            if matched:
                keys.extend(matched)
            else:
                print(f"  no manifest entries for tool '{target}'")
    return keys


def main():
    grimoire_root = Path(sys.argv[1])
    targets = sys.argv[2:]

    if not targets:
        print("Usage: cast --accept <tool|tool/file> [...]")
        sys.exit(1)

    tome_root = grimoire_root / "tome"
    manifest = _load_manifest(tome_root)
    keys = resolve_targets(manifest, targets)

    if not keys:
        sys.exit(1)

    dirty = False
    for key in keys:
        tool, filename = key.split("/", 1)
        tome_file = tome_root / key
        rite_file = grimoire_root / "rites" / tool / filename

        if not tome_file.exists():
            print(f"  {key}: tome file missing — skipping")
            continue

        current_hash = _hash_file(tome_file)
        if current_hash == manifest.get(key):
            print(f"  {key}: not modified — skipping")
            continue

        if not rite_file.exists():
            print(f"  {key}: no matching source in rites/{tool}/ — needs manual reconciliation")
            continue

        shutil.copy2(tome_file, rite_file)
        manifest[key] = current_hash
        dirty = True
        print(f"  accepted {key} → rites/{tool}/{filename}")

    if dirty:
        _save_manifest(tome_root, manifest)


if __name__ == "__main__":
    main()
