import click
from .notes import notes
from .ingest import ingest


# ---------------------------------------------------------------------------
# Root CLI entrypoint
#
# This function defines the top‑level `pke` command. All subcommands
# (e.g., `pke notes list`) are registered beneath this group.
#
# Design goals:
#   • Keep the root command minimal and declarative
#   • Provide a clear extension point for future command groups
#   • Avoid embedding business logic at the top level
#
# Contributors can add new command groups (e.g., `pke ingest`, `pke debug`)
# by importing them and registering them below.
# ---------------------------------------------------------------------------
@click.group()
def cli():
    """Personal Knowledge Engine command-line interface."""
    # No logic here — this function serves as a namespace for subcommands.
    pass


# ---------------------------------------------------------------------------
# Register subcommands
#
# Each subcommand group (e.g., notes, ingest, debug) is defined in its own
# module under pke/cli/. This keeps the CLI modular and prevents the root
# entrypoint from becoming a monolith.
#
# Adding a new command group is as simple as:
#   from .<module> import <group>
#   cli.add_command(<group>)
# ---------------------------------------------------------------------------
cli.add_command(notes)
cli.add_command(ingest)
