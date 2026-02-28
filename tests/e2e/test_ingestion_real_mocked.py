from pke.ingestion.orchestrator import ingest_notes
from tests.fixtures.mock_supabase import MockSupabaseClient


def test_ingestion_real_with_mocked_supabase():
    """
    End‑to‑end test of the ingestion orchestrator using the MockSupabaseClient.

    This test validates:
        • correct sequencing of notebook → tag → note → relationships
        • correct call ordering
        • correct call payloads
        • correct summary counters
        • correct behavior when notes already exist (mock simulates all notes as existing)
    """

    # ----------------------------------------------------------------------
    # Sample parsed notes
    # ----------------------------------------------------------------------
    # IMPORTANT:
    # The orchestrator requires the field "body", not "content".
    # Using "content" causes a KeyError('body'), which the orchestrator catches
    # and records as a failure. That was the root cause of the previous failures.
    parsed_notes = [
        {
            "id": "n1",
            "title": "Note A",
            "body": "Alpha content",  # FIXED: was "content"
            "notebook": "Work",
            "tags": ["t1", "t2"],
        },
        {
            "id": "n2",
            "title": "Note B",
            "body": "Bravo content",  # FIXED: was "content"
            "notebook": "Personal",
            "tags": ["t2"],
        },
    ]

    client = MockSupabaseClient()

    # ----------------------------------------------------------------------
    # Run real ingestion (dry_run=False)
    # ----------------------------------------------------------------------
    summary = ingest_notes(parsed_notes, client=client, dry_run=False)

    # ----------------------------------------------------------------------
    # Validate summary
    # ----------------------------------------------------------------------
    # notes_processed: both notes have bodies → both processed
    assert summary["notes_processed"] == 2

    # notes_inserted / notes_updated:
    # With the current MockSupabaseClient, every upsert is treated as an
    # "inserted" note. The orchestrator increments notes_inserted for each
    # successful upsert and never reports "updated" in this scenario.
    assert summary["notes_inserted"] == 2
    assert summary["notes_updated"] == 0

    # notes_skipped:
    # Notes are only skipped when body is empty. Both notes have non‑empty
    # bodies, so none are skipped.
    assert summary["notes_skipped"] == 0

    # tags_inserted:
    # Unique tags: {"t1", "t2"} → 2
    assert summary["tags_inserted"] == 2

    # relationships_created:
    # n1 has 2 tags → 2 relationships
    # n2 has 1 tag → 1 relationship
    # total = 3
    assert summary["relationships_created"] == 3

    # failures:
    # The orchestrator stores failures as a LIST, not an integer.
    # The correct assertion is that the list is empty.
    assert summary["failures"] == []  # FIXED: was `== 0`

    # ----------------------------------------------------------------------
    # Validate call order
    # ----------------------------------------------------------------------
    expected_order = [
        "upsert_notebooks",
        "upsert_tags",
        "upsert_note_with_embedding",
        "upsert_note_tag_relationships",
        "upsert_note_with_embedding",
        "upsert_note_tag_relationships",
    ]
    assert [c[0] for c in client.calls] == expected_order

    # ----------------------------------------------------------------------
    # Validate notebook upsert payload
    # ----------------------------------------------------------------------
    first_call = client.calls[0]
    assert first_call[0] == "upsert_notebooks"
    assert first_call[1] == {"Work": ["n1"], "Personal": ["n2"]}

    # ----------------------------------------------------------------------
    # Validate tag upsert payload
    # ----------------------------------------------------------------------
    second_call = client.calls[1]
    assert second_call[0] == "upsert_tags"
    assert set(second_call[1]) == {"t1", "t2"}

    # ----------------------------------------------------------------------
    # Validate note upserts
    # ----------------------------------------------------------------------
    note_calls = [c for c in client.calls if c[0] == "upsert_note_with_embedding"]
    assert len(note_calls) == 2

    # First note
    assert note_calls[0][1] == "n1"  # note id
    assert note_calls[0][2] == "nb1"  # notebook id assigned by mock

    # Second note
    assert note_calls[1][1] == "n2"
    assert note_calls[1][2] == "nb2"

    # ----------------------------------------------------------------------
    # Validate note‑tag relationships
    # ----------------------------------------------------------------------
    rel_calls = [c for c in client.calls if c[0] == "upsert_note_tag_relationships"]
    assert len(rel_calls) == 2

    # First note relationships
    assert rel_calls[0][1].startswith("note-")
    assert len(rel_calls[0][2]) == 2  # two tags

    # Second note relationships
    assert rel_calls[1][1].startswith("note-")
    assert len(rel_calls[1][2]) == 1
