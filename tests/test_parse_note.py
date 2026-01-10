from ingestion.parse_note import parse_note
import os


def test_basic():
    filepath = os.path.join(os.path.dirname(__file__), "fixtures", "real_note_1.md")
    result = parse_note(filepath)
    print("✅ Parsed real Joplin note")
    print(result)


if __name__ == "__main__":
    test_basic()
