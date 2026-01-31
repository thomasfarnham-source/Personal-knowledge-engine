"""
logging_utils.py

A small collection of logging helpers used across the PKE project.

Milestone 8.7.2 introduces high‑level verbose logging for the CLI and
ingestion pipeline. These helpers keep logging consistent, centralized,
and contributor‑friendly.

This module intentionally avoids any heavy logging frameworks. The goal
is to provide lightweight, predictable output that works well with Typer
and remains easy for new contributors to understand.
"""

import typer


def log_verbose(message: str, verbose: bool) -> None:
    """
    Print a high‑level progress message when verbose mode is enabled.

    Parameters
    ----------
    message : str
        The human‑readable message to display. These messages should be
        short, plain‑English descriptions of what the pipeline is doing
        (e.g., "Loading note...", "Generating embedding...").

    verbose : bool
        Whether verbose mode is active. When False, this function does
        nothing. When True, the message is printed using Typer's echo
        function for consistent CLI output.

    Notes
    -----
    - This helper is intentionally minimal. It avoids timestamps,
      prefixes, or formatting beyond what the caller provides.
    - Debug‑level output is handled separately inside CLI code and
      ingestion modules; this helper is strictly for verbose mode.
    """
    if verbose:
        typer.echo(message)
