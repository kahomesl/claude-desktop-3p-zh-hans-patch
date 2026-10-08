"""Test package.

Puts ``src/`` on ``sys.path`` so the suite runs from a checkout with no
environment setup:

    python3 -m unittest discover -s tests -t .
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
