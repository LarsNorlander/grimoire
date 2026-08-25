"""Cheatsheet content model for grimoire rites.

Rites emit **data** — pages, sections, entries — and never markup. `grimoire
scribe` serializes that data to JSON; rendering happens in `homepage`, which
reads these files and is the only thing that knows what a keycap looks like.

The model mirrors `homepage/schemas/cheatsheet.schema.json` field for field,
which is why it serializes straight across. That schema is the contract: it
sets `additionalProperties: false` and the reader parses with
`DisallowUnknownFields`, so an extra key here is a hard error there, not a
silently dropped field. Add a field to one, add it to the other.

The model is deliberately small. Nearly every config surface grimoire manages
reduces to "groups of (keys, what it does)" — tmux binds, AeroSpace mode
bindings, ghostty keybinds, git aliases, zsh aliases. Anything that doesn't
fit that shape belongs in a `body`, which is markdown prose and the schema's
one escape hatch.
"""

import json
from dataclasses import dataclass, field

# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────
#
# Optional fields default to empty and are omitted on serialization, matching
# the `omitempty` tags on homepage's Go structs.


@dataclass(frozen=True)
class DocEntry:
    """One binding: the keys, what it does, and an optional qualifier.

    `keys` is split into individual keycaps by the reader on " + ", " / ",
    " , " and " then " — so "prefix + v" renders as two caps and
    "h / j / k / l" as four. A string with no separator stays one cap, which
    is what keeps `alt-shift-s` and `git push` intact. Spell chords with
    `chord()` and join them with those separators; don't invent others.

    `note` is for per-entry caveats that aren't part of the description —
    "repeatable", "no prefix", "tmux default".
    """
    keys: str
    description: str
    note: str | None = None


@dataclass
class DocSection:
    """One group of entries, optionally introduced by prose.

    A section needs entries or a `body`; an empty one is a validation error
    downstream rather than something the reader quietly skips.
    """
    title: str
    entries: list[DocEntry] = field(default_factory=list)
    note: str | None = None
    body: str | None = None


@dataclass
class DocPage:
    """One cheatsheet.

    `summary` is the single line under the title; `body` is markdown prose for
    anything longer. `note` is a short plain-text qualifier — not markdown.
    `generator` is stamped by `grimoire scribe`, so rites leave it unset.
    """
    title: str
    sections: list[DocSection] = field(default_factory=list)
    summary: str | None = None
    tags: list[str] = field(default_factory=list)
    note: str | None = None
    body: str | None = None
    source: str | None = None  # e.g. "rites/tmux/tmux.conf" — provenance
    generator: str | None = None

    def populated(self) -> list[DocSection]:
        """Sections that carry content.

        Config files have plenty of comment headers over non-binding settings
        (tmux's "Terminal behavior", "Status bar"). Those parse into empty
        sections; dropping them here means parsers don't each need to, and
        keeps grimoire from emitting a section the reader would reject.
        """
        return [s for s in self.sections if s.entries or s.body]

    def entry_count(self) -> int:
        return sum(len(s.entries) for s in self.populated())


# ─────────────────────────────────────────────────────────────────────────────
# Serialization
# ─────────────────────────────────────────────────────────────────────────────


def _prune(mapping: dict) -> dict:
    """Drop empty optional fields, mirroring Go's `omitempty`."""
    return {k: v for k, v in mapping.items() if v not in (None, "", [], {})}


def to_dict(page: DocPage) -> dict:
    """The page as a schema-shaped dict, empty sections already dropped."""
    return _prune({
        "title": page.title,
        "summary": page.summary,
        "tags": list(page.tags),
        "note": page.note,
        "body": page.body,
        "source": page.source,
        "generator": page.generator,
        "sections": [
            _prune({
                "title": section.title,
                "note": section.note,
                "body": section.body,
                "entries": [
                    _prune({
                        "keys": entry.keys,
                        "description": entry.description,
                        "note": entry.note,
                    })
                    for entry in section.entries
                ],
            })
            for section in page.populated()
        ],
    })


def dumps(page: DocPage) -> str:
    """Serialize a page, newline-terminated so the file is diffable."""
    return json.dumps(to_dict(page), indent=2, ensure_ascii=False) + "\n"


def problems(page: DocPage) -> list[str]:
    """Every problem with a page, each naming the field it applies to.

    Mirrors `Doc.Validate` in homepage: reporting all of them at once means a
    rite author fixes a page in one pass instead of one error per run. This is
    the same check the reader runs, moved upstream — a page that fails here
    would fail to load there.
    """
    found: list[str] = []
    sections = page.populated()

    if not page.title.strip():
        found.append("title: required, must not be empty")
    if not sections and not (page.body or "").strip():
        found.append("needs at least one of sections or body, "
                     "otherwise the page has no content")
    for i, tag in enumerate(page.tags):
        if not tag.strip():
            found.append(f"tags[{i}]: must not be empty")

    for i, section in enumerate(sections):
        at = f"sections[{i}]"
        if not section.title.strip():
            found.append(f"{at}.title: required, must not be empty")
        for j, entry in enumerate(section.entries):
            where = f"{at}.entries[{j}]"
            if not entry.keys.strip():
                found.append(f"{where}.keys: required, must not be empty")
            if not entry.description.strip():
                found.append(f"{where}.description: required, must not be empty")
    return found


# ─────────────────────────────────────────────────────────────────────────────
# Key display
# ─────────────────────────────────────────────────────────────────────────────
#
# Every tool spells chords differently ("alt-shift-semicolon", "C-Space",
# "cmd+shift+t"), so tokenizing is the rite's job. Turning a token into
# something readable is not — that mapping is shared, and lives here.

_MODIFIERS = {
    "alt": "⌥", "opt": "⌥", "option": "⌥", "m": "⌥",
    "shift": "⇧", "s": "⇧",
    "cmd": "⌘", "command": "⌘", "super": "⌘",
    "ctrl": "⌃", "control": "⌃", "c": "⌃",
}

_NAMED = {
    "semicolon": ";", "minus": "-", "equal": "=", "plus": "+", "slash": "/",
    "backslash": "\\", "comma": ",", "period": ".", "quote": "'",
    "backtick": "`", "leftsquarebracket": "[", "rightsquarebracket": "]",
    "esc": "⎋", "escape": "⎋", "tab": "⇥", "enter": "↩", "return": "↩",
    "backspace": "⌫", "delete": "⌦", "space": "Space",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
    "pageup": "⇞", "pagedown": "⇟", "home": "↖", "end": "↘",
}


def chord(parts: list[str]) -> str:
    """Render one chord from its already-split tokens.

    Modifiers collapse into a glyph run and the final key follows, so
    `["alt", "shift", "semicolon"]` becomes `⌥⇧;`. Unrecognized tokens pass
    through untouched — an unknown key name is better shown verbatim than
    guessed at or dropped.
    """
    mods, keys = [], []
    last = len(parts) - 1
    for i, raw in enumerate(parts):
        token = raw.strip()
        if not token:
            continue
        low = token.lower()
        # A trailing token is the key, even when it collides with a modifier
        # abbreviation ("alt-s" ends in s, but s is the key there).
        if low in _MODIFIERS and i != last:
            mods.append(_MODIFIERS[low])
        else:
            keys.append(_NAMED.get(low, token))
    return "".join(mods) + "".join(keys)
