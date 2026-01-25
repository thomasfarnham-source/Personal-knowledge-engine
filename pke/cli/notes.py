"""
Legacy notes CLI module (deprecated in Milestone 8).

This module previously defined the `pke notes` Click command group and
its subcommands:

    • pke notes list
    • pke notes show <id>
    • pke notes search "<query>"

Milestone 8 migrates the CLI to Typer and introduces a new, canonical
notes CLI in:

    pke/cli/notes_cli.py

That Typer-based module now owns the `pke notes ...` surface, including
the `notes upsert` command and future list/show/search commands.

This file is intentionally kept as a placeholder and potential home for
non-CLI note utilities (e.g., shared helpers for parsing, formatting, or
display), but it no longer defines any CLI entrypoints.
"""

# NOTE:
#   This module no longer exposes a Click `notes` group.
#   All note-related CLI commands should be implemented in:
#
#       pke/cli/notes_cli.py
#
#   If you need shared logic for those commands (e.g., formatting a note
#   for display), you can add plain functions here and import them from
#   notes_cli.py.
#
# Example (future):
#
#   def format_note_for_cli(note: dict) -> str:
#       ...
#
#   # in notes_cli.py:
#   # from .notes import format_note_for_cli
#
# For now, this module is intentionally empty of runtime behavior.
