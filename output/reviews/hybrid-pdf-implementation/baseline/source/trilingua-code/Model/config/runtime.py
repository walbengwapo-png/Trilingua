"""Process-level safeguards for the Python translation service."""

from __future__ import annotations

import sys
from typing import TextIO


def configure_utf8_output(stream: TextIO) -> None:
    """Make diagnostic output unable to crash a request on Windows.

    Windows services often inherit a legacy cp1252 console.  Pipeline logging
    includes language arrows and source text in Cebuano/Filipino, so a normal
    ``print`` can otherwise raise ``UnicodeEncodeError`` and turn a successful
    translation into HTTP 500.  Backslash replacement is a last-resort safety
    net for an output sink that rejects UTF-8; it never changes document data.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            # Some embedded/closed streams cannot be reconfigured.  Logging
            # must remain non-fatal in that case.
            pass


def configure_process_output() -> None:
    """Configure both process output streams before pipeline imports."""
    configure_utf8_output(sys.stdout)
    configure_utf8_output(sys.stderr)
