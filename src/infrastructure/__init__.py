"""Infrastructure adapters (I/O, external APIs)."""

from pathlib import Path

# Repository root (parent of ``src``): project ``.env``, default ``cache/``, etc.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
