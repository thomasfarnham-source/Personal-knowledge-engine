import os


# Function to classify all .md files in the Joplin sync folder by their type_
def classify_joplin_files(sync_dir):
    # Initialize counters for each known Joplin type and special cases
    counts = {
        "type_1_folder": 0,  # Standard folders (notebooks)
        "type_2_note": 0,  # True notes
        "type_4_resource": 0,  # Resource metadata (PDFs, images, etc.)
        "type_5_tag": 0,  # Tag definitions
        "type_6_note_tag": 0,  # Note–tag relationships
        "type_13_note_resource": 0,  # Note–resource relationships
        "unknown": 0,  # Files with no recognizable type_
        "note_like_type_1": 0,  # Legacy Evernote notes misclassified as folders
    }

    # Loop through all .md files in the sync folder
    for filename in os.listdir(sync_dir):
        if not filename.endswith(".md"):
            continue  # Skip non-markdown files

        path = os.path.join(sync_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

                # Check for each known type
                if "type_: 2" in content:
                    counts["type_2_note"] += 1
                elif "type_: 1" in content:
                    # Heuristic: treat as note if it has Evernote-like metadata or URLs
                    if any(
                        k in content.lower()
                        for k in [
                            "source: evernote",
                            "source_application: net.cozic.joplin",
                            "source_url:",
                            "http://",
                            "https://",
                        ]
                    ):
                        counts["note_like_type_1"] += 1
                    else:
                        counts["type_1_folder"] += 1
                elif "type_: 4" in content:
                    counts["type_4_resource"] += 1
                elif "type_: 5" in content:
                    counts["type_5_tag"] += 1
                elif "type_: 6" in content:
                    counts["type_6_note_tag"] += 1
                elif "type_: 13" in content:
                    counts["type_13_note_resource"] += 1
                else:
                    counts["unknown"] += 1  # No recognizable type_
        except Exception as e:
            print(f"⚠️ Error reading {filename}: {e}")

    # Print summary of file types found
    print("\n📊 Joplin Sync Folder Summary:")
    for k, v in counts.items():
        print(f"{k:22}: {v}")


# Function to summarize the contents of the .resource folder (attachments)
def summarize_resource_folder(resource_dir):
    total = 0
    by_ext = {}  # Count by file extension

    for filename in os.listdir(resource_dir):
        total += 1
        ext = os.path.splitext(filename)[1].lower()
        by_ext[ext] = by_ext.get(ext, 0) + 1

    # Print summary of resource file types
    print("\n📎 .resource Folder Summary:")
    print(f"Total files: {total}")
    for ext, count in sorted(by_ext.items()):
        print(f"{ext or '[no extension]':10}: {count}")


# 🔧 Update these paths to match your local setup
sync_folder = r"C:\Users\thoma\OneDrive\Apps\Joplin"
resource_folder = os.path.join(sync_folder, ".resource")

# Run both classification functions
classify_joplin_files(sync_folder)
summarize_resource_folder(resource_folder)
