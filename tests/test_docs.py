"""Cheatsheet tests: the shared model and a smoke test per documenting rite.

The smoke tests read the real `rites/` directory on purpose. A config file
that changes shape should fail here, before `grimoire scribe` emits a page
homepage rejects.

Run with: uv run python -m unittest
"""

import unittest
from pathlib import Path

from arcana import docs, rites
from arcana.tome import RiteSkipped

REPO = Path(__file__).resolve().parents[1]


class Chord(unittest.TestCase):
    def test_modifiers_collapse_and_named_keys_render(self):
        self.assertEqual(docs.chord(["alt", "shift", "semicolon"]), "⌥⇧;")
        self.assertEqual(docs.chord(["C", "Space"]), "⌃Space")
        self.assertEqual(docs.chord(["cmd", "enter"]), "⌘↩")

    def test_trailing_token_is_the_key_even_if_it_looks_like_a_modifier(self):
        self.assertEqual(docs.chord(["alt", "s"]), "⌥s")
        self.assertEqual(docs.chord(["c"]), "c")

    def test_unknown_tokens_pass_through(self):
        self.assertEqual(docs.chord(["alt", "F13"]), "⌥F13")


class Model(unittest.TestCase):
    def page(self, **kw) -> docs.DocPage:
        return docs.DocPage(title="T", **kw)

    def test_problems_reports_every_missing_field_at_once(self):
        page = docs.DocPage(
            title=" ",
            tags=["ok", ""],
            sections=[
                docs.DocSection(
                    title="", entries=[docs.DocEntry(keys="", description="")]
                )
            ],
        )
        found = docs.problems(page)
        self.assertEqual(len(found), 5, found)

    def test_empty_sections_are_dropped_not_reported(self):
        page = self.page(
            sections=[
                docs.DocSection(title="Empty"),
                docs.DocSection(title="Full", body="x"),
            ]
        )
        self.assertEqual([s.title for s in page.populated()], ["Full"])
        self.assertEqual(docs.problems(page), [])

    def test_page_needs_sections_or_body(self):
        self.assertIn("no content", docs.problems(self.page())[0])
        self.assertEqual(docs.problems(self.page(body="prose")), [])

    def test_serialization_omits_empty_optionals(self):
        page = self.page(
            sections=[docs.DocSection(title="S", entries=[docs.DocEntry("k", "d")])]
        )
        self.assertEqual(
            docs.to_dict(page),
            {
                "title": "T",
                "sections": [
                    {"title": "S", "entries": [{"keys": "k", "description": "d"}]}
                ],
            },
        )
        self.assertTrue(docs.dumps(page).endswith("\n"))


class RiteSmoke(unittest.TestCase):
    """Every rite that registers doc() must build a valid, non-empty page."""

    def pages_for(self, profile: str):
        for path in rites.discover(REPO):
            try:
                ctx = rites.load_rite(path, profile, REPO)
            except RiteSkipped:
                continue
            for page in ctx.registered_docs():
                yield path.parent.name, page

    def test_documenting_rites_exist(self):
        tools = {tool for tool, _ in self.pages_for("work")}
        self.assertTrue(
            tools, "no rite registers doc(); remove this suite if that is intended"
        )

    def test_pages_are_valid_and_populated_under_each_profile(self):
        for profile in rites.VALID_PROFILES:
            for tool, page in self.pages_for(profile):
                with self.subTest(tool=tool, profile=profile):
                    self.assertEqual(docs.problems(page), [])
                    self.assertGreater(
                        page.entry_count(), 0, "parser found no bindings"
                    )
                    self.assertTrue(page.source, "page should name its source file")


if __name__ == "__main__":
    unittest.main()
