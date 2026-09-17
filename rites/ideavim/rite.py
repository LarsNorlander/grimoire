"""Applies ideavimrc, and derives a cheatsheet from that same file.

Three things in the file carry intent the `map` lines don't: the `" -- Title`
comment headers that group them, the `g:WhichKeyDesc_*` assignments that name
individual mappings, and the IDE action inside `<Action>(...)`. The parser
prefers them in that order and only falls back to showing the raw right-hand
side, so a mapping is never described by a guess.
"""

import re

from arcana.docs import DocEntry, DocPage, DocSection, chord
from arcana.tome import RiteContext

_LEADER = re.compile(r'^\s*let\s+mapleader\s*=\s*[\'"](?P<value>.*)[\'"]')
_WHICHKEY = re.compile(r'^\s*let\s+g:WhichKeyDesc_\w+\s*=\s*[\'"](?P<value>.+)[\'"]')
_MAP = re.compile(
    r"^\s*(?P<mode>[nvxio]?)(?:nore)?map\s+(?P<lhs>\S+)\s+(?P<rhs>.+?)\s*$"
)
_HEADER = re.compile(r'^\s*"\s*(?P<dashes>-{2,})\s*(?P<title>.+?)\s*$')
_ACTION = re.compile(r"^<Action>\((?P<name>\w+)\)$")
_TOKEN = re.compile(r"<[^>]+>|.")

_MODES = {"n": "normal", "v": "visual", "x": "visual", "i": "insert", "o": "operator"}


def _leader_display(value: str) -> str:
    return "Space" if value == " " else value


def _key_display(token: str, leader: str) -> str:
    """One `<...>` group or bare character as something readable."""
    if not token.startswith("<"):
        return token
    inner = token[1:-1]
    if inner.lower() == "leader":
        return leader
    return chord(inner.split("-"))


def _keys(lhs: str, leader: str) -> str:
    """Render a mapping's left-hand side.

    Only a leader prefix becomes a separate keycap. Splitting every sequence
    would turn `gd` into "g then d", which is not how anyone reads a vim
    mapping — but `<leader>ff` genuinely is "Space, then ff".
    """
    tokens = _TOKEN.findall(lhs)
    parts = [_key_display(t, leader) for t in tokens]
    if tokens and tokens[0].lower() == "<leader>":
        rest = "".join(parts[1:])
        return f"{parts[0]} then {rest}" if rest else parts[0]
    return "".join(parts)


def _humanize_action(name: str) -> str:
    """`ActivateTerminalToolWindow` -> `Activate terminal tool window`."""
    words = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|\d+", name)
    if not words:
        return name
    return " ".join([words[0]] + [w.lower() for w in words[1:]])


def build_docs(*, rite_dir, **_) -> DocPage:
    text = (rite_dir / "ideavimrc").read_text()

    leader = "\\"
    descriptions: dict[str, str] = {}
    for line in text.splitlines():
        if match := _LEADER.match(line):
            leader = _leader_display(match.group("value"))
        elif match := _WHICHKEY.match(line):
            lhs, _, desc = match.group("value").partition(" ")
            if desc:
                descriptions[lhs] = desc.strip()

    sections: list[DocSection] = []
    current: DocSection | None = None
    group: str | None = None
    sub: str | None = None

    for line in text.splitlines():
        if match := _HEADER.match(line):
            if len(match.group("dashes")) <= 2:
                group, sub = match.group("title"), None
            else:
                sub = match.group("title")
            current = None
            continue

        match = _MAP.match(line)
        if not match:
            continue
        lhs, rhs, mode = match.group("lhs"), match.group("rhs"), match.group("mode")

        if description := descriptions.get(lhs):
            pass
        elif action := _ACTION.match(rhs):
            description = _humanize_action(action.group("name"))
        else:
            description = rhs

        if current is None:
            title = " · ".join(x for x in (group, sub) if x) or "Mappings"
            current = DocSection(title=title)
            sections.append(current)
        current.entries.append(
            DocEntry(
                keys=_keys(lhs, leader),
                description=description,
                note=_MODES.get(mode),
            )
        )

    return DocPage(
        title="IdeaVim",
        summary=f"Vim mappings inside JetBrains IDEs. The leader is {leader}.",
        tags=["ideavim", "vim", "jetbrains"],
        source="rites/ideavim/ideavimrc",
        sections=sections,
    )


def rite(ctx: RiteContext) -> None:
    ctx.copy("ideavimrc")
    ctx.link("ideavimrc", "~/.config/ideavim/ideavimrc")
    ctx.doc(build_docs)
