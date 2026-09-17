"""Builds aerospace.toml from base config + the profile overlay.

Also derives a cheatsheet from the *merged* result rather than from base.toml,
so the page shows what this machine's profile actually produces — overlay
bindings included, and no bindings the current profile doesn't have.
"""

import re

import tomlkit
from tomlkit.items import Table

from arcana.docs import DocEntry, DocPage, DocSection, chord
from arcana.tome import RiteContext


def merge_into_table(base_table, overlay_table):
    """Merge overlay keys into a tomlkit table."""
    for key, value in overlay_table.items():
        if key in base_table:
            base_val = base_table[key]
            if isinstance(base_val, dict) and isinstance(value, dict):
                merge_into_table(base_val, value)
            elif isinstance(base_val, list) and isinstance(value, list):
                base_val.extend(value)
            else:
                base_table[key] = value
        else:
            base_table.add(key, value)


def apply_directives(doc) -> None:
    """Consume the [grimoire] table: instructions for this rite, not AeroSpace.

    `service-d` assembles the service mode's `d` as base's list, then the
    profile's `before-exit` entries (already concatenated in by the overlay
    merge), then `exit`. Anything else under [grimoire] is a typo: fail rather
    than let a misnamed directive silently do nothing.
    """
    directives = doc.pop("grimoire", {})
    service_d = directives.pop("service-d", {})
    exit_tail = list(service_d.pop("exit"))
    before_exit = list(service_d.pop("before-exit", []))
    leftover = list(service_d) + list(directives)
    if leftover:
        raise ValueError(f"unknown [grimoire] directive(s): {', '.join(leftover)}")

    binding: Table = doc["mode"]["service"]["binding"]
    merged = tomlkit.item(list(binding["d"]) + before_exit + exit_tail)
    merged.multiline(True)
    binding["d"] = merged


def build_aerospace(*, profile, rite_dir, **_):
    with open(rite_dir / "base.toml") as f:
        doc = tomlkit.load(f)

    overlay_path = rite_dir / f"{profile}.toml"
    if overlay_path.exists():
        with open(overlay_path) as f:
            merge_into_table(doc, tomlkit.load(f))

    apply_directives(doc)
    return tomlkit.dumps(doc)


# ── Cheatsheet derivation ───────────────────────────────────────────────────
#
# base.toml groups its bindings two ways, and both work as section headers:
# plain comments ("# selection", "# move") and AeroSpace doc links
# ("# See: .../commands#focus"), whose URL fragment names the command family.
# Reading the fragment is what gives main mode any structure at all — every
# comment in it is a doc link.

# JankyBorders tinting rides along with mode switches. It's visual plumbing,
# not the point of the binding, so it's dropped when anything else remains.
_PLUMBING = "tint-borders"

_SEE_FRAGMENT = re.compile(r"https?://\S*#([\w-]+)")
_CANTRIP = re.compile(r"cantrips/[^/]+/(.+)$")


def _comment_text(raw: str) -> str:
    return raw.lstrip("#").strip()


def _humanize(cmd: str) -> str:
    """Shorten one AeroSpace command for display."""
    if cmd.startswith("exec-and-forget "):
        rest = cmd[len("exec-and-forget ") :].strip()
        if m := _CANTRIP.search(rest):
            return m.group(1)
        return rest
    return cmd


def _collapse(cmds: list[str]) -> str:
    """Join commands, folding consecutive repeats of one verb into xN.

    The service-mode `d` binding is ten move-workspace-to-monitor calls in a
    row; spelling each out would bury the only part worth reading.
    """
    runs: list[list] = []
    for cmd in cmds:
        verb = cmd.split(" ", 1)[0]
        if runs and runs[-1][0] == verb:
            runs[-1][1] += 1
        else:
            runs.append([verb, 1, cmd])
    return " → ".join(
        f"{verb} ×{count}" if count > 1 else full for verb, count, full in runs
    )


def _describe(value) -> str:
    cmds = [str(value)] if isinstance(value, str) else [str(v) for v in value]
    if not cmds:
        return "disabled — suppresses the macOS default"
    human = [_humanize(c) for c in cmds]
    if meaningful := [h for h in human if not h.startswith(_PLUMBING)]:
        human = meaningful
    return _collapse(human)


def _binding_keys(path) -> dict[str, set[str]]:
    """mode -> binding keys declared in a single (unmerged) TOML file."""
    if not path.exists():
        return {}
    with open(path) as f:
        doc = tomlkit.load(f)
    out: dict[str, set[str]] = {}
    for mode, table in doc.get("mode", {}).items():
        if (binding := table.get("binding")) is not None:
            out[mode] = {str(k).strip() for k in binding}
    return out


class _Grouper:
    """Turns a binding table's comment stream into section titles.

    Comments arrive as blocks of consecutive lines. Within a block, `# text`
    sets the group, `## text` refines it, extra lines become the section note,
    and bare doc links contribute a label only when nothing better is present.
    """

    def __init__(self, mode: str):
        self.mode = mode
        self.group: str | None = None
        self.sub: str | None = None
        self.note: str | None = None
        self._block: list[tuple[int, str]] = []

    def comment(self, raw: str) -> None:
        stripped = raw.lstrip()
        level = len(stripped) - len(stripped.lstrip("#"))
        self._block.append((level, stripped.lstrip("#").strip()))

    def flush(self) -> bool:
        """Apply the buffered block. True if the group changed."""
        block, self._block = self._block, []
        if not block:
            return False
        # A "See:" link is a reference, not a name — unless it's all we have.
        plain = [(lvl, t) for lvl, t in block if not _SEE_FRAGMENT.search(t)]
        if not plain:
            if m := _SEE_FRAGMENT.search(block[0][1]):
                self.group, self.sub, self.note = (
                    m.group(1).replace("-", " "),
                    None,
                    None,
                )
                return True
            return False
        primary = [t for lvl, t in plain if lvl < 2]
        refine = [t for lvl, t in plain if lvl >= 2]
        if primary:
            self.group = primary[0].rstrip(".")
            self.sub = None
            self.note = " ".join(primary[1:]) or None
        if refine:
            self.sub = refine[0].rstrip(".")
        return True

    def title(self) -> str:
        return " · ".join(x for x in (self.mode, self.group, self.sub) if x)


def build_docs(*, profile, rite_dir, **_) -> DocPage:
    # Parse the same text the rite writes, so the page can't disagree with the
    # config: one merge, two outputs.
    doc = tomlkit.parse(build_aerospace(profile=profile, rite_dir=rite_dir))
    base_keys = _binding_keys(rite_dir / "base.toml")
    overlay_keys = _binding_keys(rite_dir / f"{profile}.toml")

    sections: list[DocSection] = []
    for mode, mode_table in doc.get("mode", {}).items():
        binding = mode_table.get("binding")
        if binding is None:
            continue
        # Keys the overlay introduces outright. Merged in without any comment
        # of their own, they'd otherwise inherit whichever group happened to
        # come last — and they're worth calling out as profile-specific anyway.
        exclusive = overlay_keys.get(mode, set()) - base_keys.get(mode, set())

        grouper = _Grouper(mode)
        current: DocSection | None = None
        overlay_section: DocSection | None = None

        for key, item in binding.value.body:
            kind = type(item).__name__
            if key is None:
                if kind == "Comment":
                    grouper.comment(item.trivia.comment)
                elif grouper.flush():
                    current = None  # blank line ended a block
                continue

            if grouper.flush():
                current = None

            entry = DocEntry(
                keys=chord(str(key).strip().split("-")),
                description=(
                    _comment_text(item.trivia.comment)
                    if item.trivia.comment
                    else _describe(item)
                ),
            )

            if str(key).strip() in exclusive:
                if overlay_section is None:
                    overlay_section = DocSection(
                        title=f"{mode} · {profile} profile",
                        note=f"Only present on the {profile} profile "
                        f"(from {profile}.toml).",
                    )
                    sections.append(overlay_section)
                overlay_section.entries.append(entry)
                continue

            if current is None:
                current = DocSection(title=grouper.title(), note=grouper.note)
                sections.append(current)
            current.entries.append(entry)

    return DocPage(
        title="AeroSpace",
        summary="Tiling window management, in three binding modes.",
        tags=["aerospace", "window-manager", "macos"],
        body="`main` is the resting mode; `service` and `arrange` are "
        "temporary modes entered from it and left with Escape — the "
        "border tint shows which one is live.",
        source=f"rites/aerospace/base.toml + {profile}.toml (merged)",
        sections=sections,
    )


def rite(ctx: RiteContext) -> None:
    ctx.write("aerospace.toml", build_aerospace)
    ctx.link("aerospace.toml", "~/.config/aerospace/aerospace.toml")
    ctx.doc(build_docs)
