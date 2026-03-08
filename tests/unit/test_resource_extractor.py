"""
Tests for pke/chunking/resource_extractor.py

Test strategy:
    - extract_resources() is tested with representative fixtures covering
      all supported resource formats and broken placeholder variants
    - ResourceResult fields are validated for correctness: clean_text,
      resource_ids, resource_types
    - Edge cases: empty input, no resources, duplicate resource IDs,
      mixed format notes, resources with no surrounding text

Fixtures are defined inline as module-level constants.
"""

from pke.chunking.resource_extractor import ResourceResult, extract_resources

# ============================================================================
# FIXTURES
# ============================================================================

# Single markdown image — standard Joplin inline image format
MARKDOWN_IMAGE = "Some text.\n![A photo](:/abc123def456)\nMore text."

# Single HTML image — alternate format used by some Joplin versions
HTML_IMAGE = 'Some text.\n<img src=":/abc123def456" width="100" />\nMore text.'

# Single audio link — Evernote-style filename with embedded timestamp
AUDIO_LINK = (
    "Some context.\n"
    "[Evernote 20150621 00:15:50.m4a](:/ee55da041f3e4ff4eb66308a2a89a8d0)\n"
    "More context."
)

# Mixed resources — markdown image followed by audio link, both in same note
# Representative of Archetype D travel notes with photos and voice memos
MIXED_RESOURCES = (
    "Day 1\n"
    "We arrived in Dublin.\n"
    "![IMG_3616.JPG](:/c09c492d04c41e7bef88260a56a8e2f0)\n"
    "Great craic.\n"
    "[Evernote 20150621 00:15:50.m4a](:/ee55da041f3e4ff4eb66308a2a89a8d0)\n"
    "End of day."
)

# Broken placeholders only — no real resource IDs present
# These are malformed image references left by failed Joplin exports
BROKEN_PLACEHOLDERS = (
    "We stopped for lunch. {picture)\n"
    "The view was incredible. (Picture)\n"
    "Then we walked on. (picture)\n"
    "There was an image here somewhere."
)

# Duplicate resource ID — same image referenced twice in one note
# Should be stored once in resource_ids and resource_types
DUPLICATE_RESOURCE = "![First](:/aabbccdd1122)\n" "Some text.\n" "![Second](:/aabbccdd1122)\n"

# Plain text with no resource references of any kind
PLAIN_TEXT = "Just some plain text.\nNo resources here.\nNothing to extract."

# Empty string — boundary condition
EMPTY = ""

# HTML image with attributes in non-standard order
# Validates that the regex does not depend on src appearing first
HTML_IMAGE_ALT_ATTRS = (
    "Text before.\n" '<img width="800" src=":/ff00aa1122334455" height="600" />\n' "Text after."
)


# ============================================================================
# RETURN TYPE TESTS
# ============================================================================


class TestResourceResultType:
    """
    extract_resources() always returns a well-formed ResourceResult instance
    regardless of input content. These tests validate the return type contract
    before any content-specific assertions.
    """

    def test_returns_resource_result_instance(self):
        """Return value is always a ResourceResult, never a raw dict or None."""
        result = extract_resources(PLAIN_TEXT)
        assert isinstance(result, ResourceResult)

    def test_clean_text_is_str(self):
        """clean_text is always a string, even when input has no resources."""
        result = extract_resources(PLAIN_TEXT)
        assert isinstance(result.clean_text, str)

    def test_resource_ids_is_list(self):
        """resource_ids is always a list, empty when no resources are found."""
        result = extract_resources(PLAIN_TEXT)
        assert isinstance(result.resource_ids, list)

    def test_resource_types_is_dict(self):
        """resource_types is always a dict, empty when no resources are found."""
        result = extract_resources(PLAIN_TEXT)
        assert isinstance(result.resource_types, dict)


# ============================================================================
# MARKDOWN IMAGE TESTS
# ============================================================================


class TestMarkdownImageExtraction:
    """
    Markdown image links in the format ![alt](:/resource_id) are the most
    common resource format in the Joplin corpus. These tests validate that
    the resource ID is extracted, the link is stripped from text, surrounding
    content is preserved, and the type is correctly classified as "image".
    """

    def test_extracts_resource_id(self):
        """Resource ID from the markdown image link is captured in resource_ids."""
        result = extract_resources(MARKDOWN_IMAGE)
        assert "abc123def456" in result.resource_ids

    def test_strips_markdown_image_from_text(self):
        """The full markdown image syntax is removed from clean_text."""
        result = extract_resources(MARKDOWN_IMAGE)
        assert "![A photo](:/abc123def456)" not in result.clean_text

    def test_preserves_surrounding_text(self):
        """Text before and after the image link is preserved in clean_text."""
        result = extract_resources(MARKDOWN_IMAGE)
        assert "Some text." in result.clean_text
        assert "More text." in result.clean_text

    def test_resource_type_is_image(self):
        """Markdown image resources are classified as type 'image'."""
        result = extract_resources(MARKDOWN_IMAGE)
        assert result.resource_types["abc123def456"] == "image"


# ============================================================================
# HTML IMAGE TESTS
# ============================================================================


class TestHtmlImageExtraction:
    """
    HTML image tags in the format <img src=":/resource_id" .../> appear in
    some Joplin notes, particularly older ones or those with rich formatting.
    These tests validate extraction, stripping, and type classification for
    the HTML image format, including attribute order variations.
    """

    def test_extracts_resource_id(self):
        """Resource ID from the HTML img tag is captured in resource_ids."""
        result = extract_resources(HTML_IMAGE)
        assert "abc123def456" in result.resource_ids

    def test_strips_html_image_from_text(self):
        """The full HTML img tag is removed from clean_text."""
        result = extract_resources(HTML_IMAGE)
        assert "<img" not in result.clean_text

    def test_preserves_surrounding_text(self):
        """Text before and after the img tag is preserved in clean_text."""
        result = extract_resources(HTML_IMAGE)
        assert "Some text." in result.clean_text
        assert "More text." in result.clean_text

    def test_resource_type_is_image(self):
        """HTML image resources are classified as type 'image'."""
        result = extract_resources(HTML_IMAGE)
        assert result.resource_types["abc123def456"] == "image"

    def test_extracts_from_html_with_varied_attributes(self):
        """
        Extraction succeeds even when src is not the first attribute.
        Validates regex does not assume attribute ordering.
        """
        result = extract_resources(HTML_IMAGE_ALT_ATTRS)
        assert "ff00aa1122334455" in result.resource_ids


# ============================================================================
# AUDIO LINK TESTS
# ============================================================================


class TestAudioLinkExtraction:
    """
    Audio links in the format [filename.m4a](:/resource_id) appear in
    Archetype E oral history notes. The filename often carries a precise
    timestamp. These tests validate extraction, stripping, and type
    classification. Timestamp parsing from filenames is handled separately
    in archetype_e.py — not tested here.
    """

    def test_extracts_resource_id(self):
        """Resource ID from the audio link is captured in resource_ids."""
        result = extract_resources(AUDIO_LINK)
        assert "ee55da041f3e4ff4eb66308a2a89a8d0" in result.resource_ids

    def test_strips_audio_link_from_text(self):
        """The full audio link syntax is removed from clean_text."""
        result = extract_resources(AUDIO_LINK)
        assert ".m4a](:/ee55da041f3e4ff4eb66308a2a89a8d0)" not in result.clean_text

    def test_preserves_surrounding_text(self):
        """Text before and after the audio link is preserved in clean_text."""
        result = extract_resources(AUDIO_LINK)
        assert "Some context." in result.clean_text
        assert "More context." in result.clean_text

    def test_resource_type_is_audio(self):
        """Audio link resources are classified as type 'audio'."""
        result = extract_resources(AUDIO_LINK)
        assert result.resource_types["ee55da041f3e4ff4eb66308a2a89a8d0"] == "audio"


# ============================================================================
# MIXED RESOURCE TESTS
# ============================================================================


class TestMixedResources:
    """
    Notes containing both image and audio resources are common in Archetype D
    travel notes. These tests validate that all resource types are extracted
    together correctly, that ordering is preserved, and that surrounding prose
    is unaffected.
    """

    def test_extracts_all_resource_ids(self):
        """Both the image and audio resource IDs are captured."""
        result = extract_resources(MIXED_RESOURCES)
        assert "c09c492d04c41e7bef88260a56a8e2f0" in result.resource_ids
        assert "ee55da041f3e4ff4eb66308a2a89a8d0" in result.resource_ids

    def test_resource_ids_in_order_of_appearance(self):
        """
        Resource IDs are stored in the order they appear in the text.
        The image appears before the audio link in the fixture.
        """
        result = extract_resources(MIXED_RESOURCES)
        image_idx = result.resource_ids.index("c09c492d04c41e7bef88260a56a8e2f0")
        audio_idx = result.resource_ids.index("ee55da041f3e4ff4eb66308a2a89a8d0")
        assert image_idx < audio_idx

    def test_correct_types_assigned(self):
        """Each resource ID is classified with the correct type."""
        result = extract_resources(MIXED_RESOURCES)
        assert result.resource_types["c09c492d04c41e7bef88260a56a8e2f0"] == "image"
        assert result.resource_types["ee55da041f3e4ff4eb66308a2a89a8d0"] == "audio"

    def test_strips_all_resource_references(self):
        """Both resource references are removed from clean_text."""
        result = extract_resources(MIXED_RESOURCES)
        assert ":/c09c492d04c41e7bef88260a56a8e2f0" not in result.clean_text
        assert ":/ee55da041f3e4ff4eb66308a2a89a8d0" not in result.clean_text

    def test_preserves_non_resource_text(self):
        """Prose content between and around resources is preserved."""
        result = extract_resources(MIXED_RESOURCES)
        assert "We arrived in Dublin." in result.clean_text
        assert "Great craic." in result.clean_text
        assert "End of day." in result.clean_text


# ============================================================================
# BROKEN PLACEHOLDER TESTS
# ============================================================================


class TestBrokenPlaceholders:
    """
    Broken image placeholders are malformed references left by failed Joplin
    exports or manual note editing. They carry no resource ID and should be
    stripped silently from clean_text without storing anything in resource_ids
    or resource_types. Four variants are observed in the corpus.
    """

    def test_strips_curly_brace_placeholder(self):
        """The {picture) variant is stripped from clean_text."""
        result = extract_resources(BROKEN_PLACEHOLDERS)
        assert "{picture)" not in result.clean_text

    def test_strips_capitalized_placeholder(self):
        """The (Picture) variant is stripped from clean_text."""
        result = extract_resources(BROKEN_PLACEHOLDERS)
        assert "(Picture)" not in result.clean_text

    def test_strips_lowercase_placeholder(self):
        """The (picture) variant is stripped from clean_text."""
        result = extract_resources(BROKEN_PLACEHOLDERS)
        assert "(picture)" not in result.clean_text

    def test_strips_bare_image_word(self):
        """The standalone word 'image' is stripped from clean_text."""
        result = extract_resources(BROKEN_PLACEHOLDERS)
        assert "image" not in result.clean_text.lower()

    def test_no_resource_ids_stored_for_placeholders(self):
        """Broken placeholders produce no entries in resource_ids."""
        result = extract_resources(BROKEN_PLACEHOLDERS)
        assert result.resource_ids == []

    def test_no_resource_types_stored_for_placeholders(self):
        """Broken placeholders produce no entries in resource_types."""
        result = extract_resources(BROKEN_PLACEHOLDERS)
        assert result.resource_types == {}


# ============================================================================
# DUPLICATE RESOURCE ID TESTS
# ============================================================================


class TestDuplicateResourceIds:
    """
    Some notes reference the same resource ID more than once — for example,
    the same image appearing in both a thumbnail and a full-size view.
    The resource ID should be stored only once in resource_ids and
    resource_types regardless of how many times it appears in the text.
    """

    def test_duplicate_id_stored_once(self):
        """A resource ID appearing twice in text is stored only once."""
        result = extract_resources(DUPLICATE_RESOURCE)
        assert result.resource_ids.count("aabbccdd1122") == 1

    def test_duplicate_type_stored_once(self):
        """A duplicate resource ID produces only one entry in resource_types."""
        result = extract_resources(DUPLICATE_RESOURCE)
        assert "aabbccdd1122" in result.resource_types


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestEdgeCases:
    """
    Boundary conditions and defensive cases. These tests ensure the extractor
    handles degenerate inputs gracefully without raising exceptions or
    returning malformed results.
    """

    def test_empty_string_returns_empty_result(self):
        """Empty input returns a ResourceResult with all fields empty."""
        result = extract_resources(EMPTY)
        assert result.clean_text == ""
        assert result.resource_ids == []
        assert result.resource_types == {}

    def test_plain_text_unchanged(self):
        """Text with no resources is returned unchanged in clean_text."""
        result = extract_resources(PLAIN_TEXT)
        assert result.clean_text == PLAIN_TEXT
        assert result.resource_ids == []

    def test_multiple_blank_lines_collapsed(self):
        """
        Three or more consecutive blank lines are collapsed to two.
        This cleans up the gaps left when resource references are stripped
        from between paragraphs.
        """
        text = "Line one.\n\n\n\n\nLine two."
        result = extract_resources(text)
        assert "\n\n\n" not in result.clean_text

    def test_result_is_stripped(self):
        """
        Leading and trailing whitespace is stripped from clean_text.
        Ensures chunks don't begin or end with blank lines after
        resource stripping.
        """
        text = "\n\n  Some text.  \n\n"
        result = extract_resources(text)
        assert result.clean_text == result.clean_text.strip()
