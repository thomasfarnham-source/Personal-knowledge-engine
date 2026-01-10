from pathlib import Path
from typing import List, Tuple

# Define the root of the Joplin sync directory
SYNC_DIR = Path(r"C:\Users\thoma\OneDrive\Apps\Joplin")


# Function to scan for .md files containing 'type_: 1' (possible notes or folders)
def scan_type1_candidates() -> List[Tuple[Path, str]]:
    type1_files: List[Tuple[Path, str]] = []

    # Recursively search for all .md files in the sync directory
    for md_file in SYNC_DIR.rglob("*.md"):
        if md_file.name.startswith(".resource-"):
            continue  # Skip resource metadata files

        try:
            with open(md_file, "r", encoding="utf-8") as f:
                text = f.read()
                if "type_: 1" in text:
                    type1_files.append((md_file, text))
        except Exception as e:
            print(f"⚠️ Error reading {md_file}: {e}")

    return type1_files


# Entry point for script execution
if __name__ == "__main__":
    candidates = scan_type1_candidates()
    print(f"🔍 Found {len(candidates)} files with type_: 1")

    # Preview the first 20 lines of up to 3 matching files
    for i, (path, text) in enumerate(candidates[:3], 1):
        print(f"\n--- File {i}: {path.name} ---")
        lines = text.splitlines()
        for line in lines[:20]:
            print(line)
