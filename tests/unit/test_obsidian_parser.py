"""
tests/unit/test_obsidian_parser.py

Unit tests for pke/parsers/obsidian_parser.py
"""

from pathlib import Path

from pke.parsers.obsidian_parser import (
    build_parsed_note,
    parse_obsidian_vault,
    read_frontmatter,
)


class TestReadFrontmatter:
    def test_valid_frontmatter_with_ingest_true(self, tmp_path: Path) -> None:
        file_path = tmp_path / "tagged.md"
        file_path.write_text(
            "---\npke-ingest: true\npke-title: Journal\n---\nBody text\n",
            encoding="utf-8",
        )

        metadata, body = read_frontmatter(file_path)

        assert metadata is not None
        assert metadata["pke-ingest"] is True
        assert metadata["pke-title"] == "Journal"
        assert body == "Body text"

    def test_frontmatter_with_ingest_false(self, tmp_path: Path) -> None:
        file_path = tmp_path / "untagged.md"
        file_path.write_text(
            "---\npke-ingest: false\n---\nBody text\n",
            encoding="utf-8",
        )

        metadata, body = read_frontmatter(file_path)

        assert metadata is not None
        assert metadata["pke-ingest"] is False
        assert body == "Body text"

    def test_frontmatter_without_ingest_key(self, tmp_path: Path) -> None:
        file_path = tmp_path / "no_ingest_key.md"
        file_path.write_text(
            "---\npke-title: Journal\n---\nBody text\n",
            encoding="utf-8",
        )

        metadata, body = read_frontmatter(file_path)

        assert metadata is not None
        assert "pke-ingest" not in metadata
        assert metadata["pke-title"] == "Journal"
        assert body == "Body text"

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        file_path = tmp_path / "plain.md"
        content = "Just plain markdown\nwithout YAML.\n"
        file_path.write_text(content, encoding="utf-8")

        metadata, body = read_frontmatter(file_path)

        assert metadata is None
        assert body == "Just plain markdown\nwithout YAML."

    def test_malformed_yaml_returns_safely(self, tmp_path: Path) -> None:
        file_path = tmp_path / "malformed.md"
        content = "---\npke-ingest: [\n---\nBody text\n"
        file_path.write_text(content, encoding="utf-8")

        metadata, body = read_frontmatter(file_path)

        assert metadata is None
        assert body == content


class TestBuildParsedNote:
    def test_note_id_is_deterministic(self, tmp_path: Path) -> None:
        file_path = tmp_path / "deterministic.md"
        file_path.write_text(
            "---\npke-ingest: true\n---\nBody text\n",
            encoding="utf-8",
        )

        note1 = build_parsed_note(file_path, tmp_path)
        note2 = build_parsed_note(file_path, tmp_path)

        assert note1 is not None
        assert note2 is not None
        assert note1.id == note2.id

    def test_note_id_differs_for_different_paths(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.md"
        file2 = tmp_path / "b.md"
        content = "---\npke-ingest: true\n---\nBody text\n"
        file1.write_text(content, encoding="utf-8")
        file2.write_text(content, encoding="utf-8")

        note1 = build_parsed_note(file1, tmp_path)
        note2 = build_parsed_note(file2, tmp_path)

        assert note1 is not None
        assert note2 is not None
        assert note1.id != note2.id

    def test_title_falls_back_to_filename_stem(self, tmp_path: Path) -> None:
        file_path = tmp_path / "fallback_title.md"
        file_path.write_text(
            "---\npke-ingest: true\n---\nBody text\n",
            encoding="utf-8",
        )

        note = build_parsed_note(file_path, tmp_path)

        assert note is not None
        assert note.title == "fallback_title"

    def test_title_uses_pke_title_when_present(self, tmp_path: Path) -> None:
        file_path = tmp_path / "titled.md"
        file_path.write_text(
            "---\npke-ingest: true\npke-title: Custom Title\n---\nBody text\n",
            encoding="utf-8",
        )

        note = build_parsed_note(file_path, tmp_path)

        assert note is not None
        assert note.title == "Custom Title"

    def test_required_fields_populated(self, tmp_path: Path) -> None:
        file_path = tmp_path / "required.md"
        frontmatter_content = (
            "---\n"
            "pke-ingest: true\n"
            "pke-title: Journal\n"
            "created_at: 2026-05-01T10:00:00Z\n"
            "updated_at: 2026-05-02T11:00:00Z\n"
            "extra_key: value\n"
            "---\n"
            "Body with [[Note Name]]\n"
        )
        file_path.write_text(frontmatter_content, encoding="utf-8")

        note = build_parsed_note(file_path, tmp_path)

        assert note is not None
        assert note.id.startswith("obsidian::")
        assert note.title == "Journal"
        assert note.body == "Body with Note Name"
        assert note.source_type == "obsidian"
        assert note.privacy_tier == 2
        assert note.participants is None
        assert note.dominant_sender is None
        assert note.thread_id is None
        assert note.thread_type is None
        assert note.person_ids is None
        assert note.source_file == "required.md"
        assert note.notebook == "Obsidian"
        assert note.created_at == "2026-05-01T10:00:00+00:00"
        assert note.updated_at == "2026-05-02T11:00:00+00:00"
        assert note.metadata == {"extra_key": "value"}


class TestParseObsidianVault:
    def test_orchestrator_counts_and_output(self, tmp_path: Path) -> None:
        tagged = tmp_path / "tagged.md"
        tagged.write_text(
            "---\npke-ingest: true\npke-title: Tagged\n---\nTagged body\n",
            encoding="utf-8",
        )

        untagged = tmp_path / "untagged.md"
        untagged.write_text(
            "---\npke-ingest: false\n---\nUntagged body\n",
            encoding="utf-8",
        )

        malformed = tmp_path / "malformed.md"
        malformed.write_text(
            "---\npke-ingest: [\n---\nBroken body\n",
            encoding="utf-8",
        )

        result = parse_obsidian_vault(tmp_path)

        assert result.files_scanned == 3
        assert result.files_tagged == 1
        assert result.files_parsed == 1
        assert len(result.notes) == 1
        assert result.notes[0].title == "Tagged"
        assert result.errors == []

    def test_hidden_directories_skipped(self, tmp_path: Path) -> None:
        visible = tmp_path / "visible.md"
        visible.write_text(
            "---\npke-ingest: true\npke-title: Visible\n---\nVisible body\n",
            encoding="utf-8",
        )

        hidden_dir = tmp_path / ".obsidian"
        hidden_dir.mkdir()
        hidden_file = hidden_dir / "hidden.md"
        hidden_file.write_text(
            "---\npke-ingest: true\npke-title: Hidden\n---\nHidden body\n",
            encoding="utf-8",
        )

        result = parse_obsidian_vault(tmp_path)

        assert result.files_scanned == 1
        assert result.files_tagged == 1
        assert result.files_parsed == 1
        assert len(result.notes) == 1
        assert result.notes[0].title == "Visible"
