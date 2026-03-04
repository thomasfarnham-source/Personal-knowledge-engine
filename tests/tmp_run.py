import sys

# allow imports from top-level package during ad-hoc execution
sys.path.append(r"c:\Users\thoma\Documents\dev\Personal-knowledge-engine")

from pathlib import Path  # noqa: E402
from pke.parsers.joplin_sync_parser import parse_sync_folder  # noqa: E402

print(parse_sync_folder(Path("tests/test_data/joplin_sync")))
