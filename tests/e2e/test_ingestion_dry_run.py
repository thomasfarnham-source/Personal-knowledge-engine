import json

from pke.ingestion.orchestrator import ingest_notes


def test_e2e_ingestion_dry_run(tmp_path):
    """
    End‑to‑end ingestion test (dry‑run mode).

    This test validates the entire ingestion pipeline WITHOUT touching Supabase:

        • Parsed notes are loaded (simulated Stage 1 output)
        • Orchestrator runs in dry‑run mode
        • Notebook resolution is exercised
        • Tag extraction is exercised
        • Relationship mapping is exercised
        • Summary shape is validated

    This ensures the ingestion pipeline is structurally correct and stable.
    """

    # ----------------------------------------------------------------------
    # 1. Create a minimal parsed_notes.json fixture in a temp directory
    # ----------------------------------------------------------------------
    parsed_notes = [
        {
            "id": "note-1",
            "title": "Test Note One",
            "body": "This is a test note.",
            "notebook": "Work",
            "tags": ["project", "urgent"],
            "metadata": {"created_time": "2024-01-01T12:00:00"},
        },
        {
            "id": "note-2",
            "title": "Test Note Two",
            "body": "Another test note.",
            "notebook": "Personal",
            "tags": ["journal"],
            "metadata": {"created_time": "2024-01-02T12:00:00"},
        },
        {
            "id": "note-3",
            "title": "Empty Body Note",
            "body": "",
            "notebook": "Work",
            "tags": ["skipme"],
            "metadata": {"created_time": "2024-01-03T12:00:00"},
        },
    ]

    parsed_path = tmp_path / "parsed_notes.json"
    parsed_path.write_text(json.dumps(parsed_notes), encoding="utf-8")

    # ----------------------------------------------------------------------
    # 2. Run orchestrator in DRY‑RUN mode
    # ----------------------------------------------------------------------
    summary = ingest_notes(
        parsed_notes=parsed_notes,
        client=None,  # dry_run=True means client is not required
        dry_run=True,
    )

    # ----------------------------------------------------------------------
    # 3. Validate summary structure
    # ----------------------------------------------------------------------
    assert "notes_processed" in summary
    assert "notes_inserted" in summary
    assert "notes_updated" in summary
    assert "notes_skipped" in summary
    assert "tags_inserted" in summary
    assert "relationships_created" in summary
    assert "failures" in summary

    # ----------------------------------------------------------------------
    # 4. Validate expected behavior
    # ----------------------------------------------------------------------
    assert summary["notes_processed"] == 3
    assert summary["notes_skipped"] == 1  # empty body
    assert summary["notes_inserted"] == 2  # dry-run simulates inserts
    assert summary["notes_updated"] == 0  # dry-run never updates

    # Tags: project, urgent, journal, skipme → 4 unique
    assert summary["tags_inserted"] == 4

    # Relationships:
    #   note-1 → 2 tags
    #   note-2 → 1 tag
    #   note-3 → 1 tag (even though skipped, dry-run still simulates)
    assert summary["relationships_created"] == 4

    # No failures expected
    assert summary["failures"] == []
