"""
tests/unit/test_obsidian_syntax.py

Unit tests for pke/parsers/obsidian_syntax.py
"""

from pke.parsers.obsidian_syntax import strip_obsidian_syntax


class TestStripObsidianSyntax:
    """Validate spec-defined Obsidian syntax stripping behavior."""

    def test_wiki_link_with_anchor(self) -> None:
        text = "[[Daily Drop 2026-04-07#★ The threat]]"
        assert strip_obsidian_syntax(text) == "Daily Drop 2026-04-07 ★ The threat"

    def test_wiki_link_without_anchor(self) -> None:
        text = "[[Note Name]]"
        assert strip_obsidian_syntax(text) == "Note Name"

    def test_wiki_link_alias(self) -> None:
        text = "[[Note Name|Display Text]]"
        assert strip_obsidian_syntax(text) == "Display Text"

    def test_wiki_link_anchor_alias(self) -> None:
        text = "[[Note Name#Heading|Display Text]]"
        assert strip_obsidian_syntax(text) == "Display Text"

    def test_highlight(self) -> None:
        text = "==Linkedin IDEA=="
        assert strip_obsidian_syntax(text) == "Linkedin IDEA"

    def test_callout(self) -> None:
        text = "> [!attention] Important text"
        assert strip_obsidian_syntax(text) == "> Important text"

    def test_callout_preserves_newline(self) -> None:
        text = "> [!note]\nMore content"
        # Current regex preserves the captured blockquote prefix including
        # trailing space before newline.
        assert strip_obsidian_syntax(text) == "> \nMore content"

    def test_comment(self) -> None:
        text = "Some text %%hidden note%% more text"
        assert strip_obsidian_syntax(text) == "Some text  more text"

    def test_combined_patterns(self) -> None:
        text = (
            "A [[Daily Drop 2026-04-07#★ The threat]] note with ==Linkedin IDEA==.\n"
            "> [!attention] callout\n"
            "plus %%hidden%% comment and [[Note Name]]."
        )
        expected = (
            "A Daily Drop 2026-04-07 ★ The threat note with Linkedin IDEA.\n"
            "> callout\n"
            "plus  comment and Note Name."
        )
        assert strip_obsidian_syntax(text) == expected

    def test_no_op_plain_markdown(self) -> None:
        text = (
            "# Header\n"
            "- list item\n"
            "Normal [external](https://example.com) link and **bold** text."
        )
        assert strip_obsidian_syntax(text) == text

    def test_code_block_preserved(self) -> None:
        text = (
            "Before\n"
            "```python\n"
            "x = '[[Note Name]] ==highlight== %%comment%% > [!note]'\n"
            "```\n"
            "After [[Real Link]]"
        )
        expected = (
            "Before\n"
            "```python\n"
            "x = '[[Note Name]] ==highlight== %%comment%% > [!note]'\n"
            "```\n"
            "After Real Link"
        )
        assert strip_obsidian_syntax(text) == expected

    def test_empty_string_returns_empty_string(self) -> None:
        assert strip_obsidian_syntax("") == ""

    def test_known_limit_unbalanced_highlight_chain(self) -> None:
        text = "==a==b==c"
        # Documents current behavior on malformed/unbalanced highlight syntax.
        assert strip_obsidian_syntax(text) == "ab==c"

    def test_known_limit_malformed_anchor_alias(self) -> None:
        text = "[[Note#heading|Display [[inner]]]]"
        # Documents current behavior on malformed wiki-link alias content.
        assert strip_obsidian_syntax(text) == "Display inner"
