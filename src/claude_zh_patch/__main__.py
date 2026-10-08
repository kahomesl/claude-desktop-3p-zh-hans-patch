"""Module entry point so ``python3 -m claude_zh_patch`` works."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
