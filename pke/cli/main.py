"""
Root entrypoint for the Personal Knowledge Engine CLI.

Milestone 8 migrates the CLI from Click to Typer to support:

    • nested command groups (e.g., `pke notes upsert`)
    • rich help output
    • type‑hint‑driven argument parsing
    • a more maintainable, contributor‑friendly structure

This module defines the top‑level `pke` command and mounts sub‑apps
from other modules under pke/cli/, such as:

    • pke/cli/notes_cli.py  →  `pke notes ...`
    • pke/cli/ingest.py     →  `pke ingest ...`
"""

import typer

# ---------------------------------------------------------------------------
# Import sub‑applications
# ---------------------------------------------------------------------------
# Each sub‑application is a Typer app defined in its own module. They are
# mounted under the root `app` to form a cohesive CLI:
#
#     pke notes  <command>
#     pke ingest <command>
# ---------------------------------------------------------------------------
from .notes_cli import notes_app
from .ingest import ingest_app

# ---------------------------------------------------------------------------
# Root CLI application
# ---------------------------------------------------------------------------
# Typer allows us to define a single root application and then attach
# sub‑applications (command groups) to it. This keeps the CLI modular
# and makes it easy for contributors to add new groups without touching
# the core logic.
#
# Example usage once everything is wired:
#
#     pke notes upsert path/to/note.md
#     pke ingest run --parsed-path parsed_notes.json
#     pke notes --help
#     pke ingest --help
#     pke --help
# ---------------------------------------------------------------------------
app = typer.Typer(
    help="Personal Knowledge Engine command-line interface.",
)


# ---------------------------------------------------------------------------
# Register sub‑applications
# ---------------------------------------------------------------------------
# Each sub‑app is mounted under a name, which becomes the first token
# after `pke` on the command line.
#
#   • `notes_app`  →  `pke notes <command>`
#   • `ingest_app` →  `pke ingest <command>`
#
# Adding a new command group is as simple as:
#
#     from .<module> import <sub_app>
#     app.add_typer(<sub_app>, name="<group-name>")
# ---------------------------------------------------------------------------
app.add_typer(notes_app, name="notes")
app.add_typer(ingest_app, name="ingest")


# ---------------------------------------------------------------------------
# Entry point for `python -m pke.cli.main`
# ---------------------------------------------------------------------------
# This block allows the module to be executed directly, which is useful
# during development or when invoking the CLI via `python -m`.
#
# In production, you may also have a console_script entry point in
# pyproject.toml or setup.cfg that points to `pke.cli.main:app`.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app()
