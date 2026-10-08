"""Community localization install tool for Claude Desktop (unofficial).

This package contains no third-party application code and no translation data.
It only operates on a local copy of an application bundle the user already has,
and on language resources the user supplies themselves.

Not affiliated with, endorsed by, or supported by Anthropic.
"""

__all__ = ["__version__"]

# The single source of truth for the version. ``pyproject.toml`` declares
# ``dynamic = ["version"]`` and reads this attribute, so the release tag
# ``v0.1.0-alpha``, what ``claude-zh-patch version`` prints, and what ends up in
# the install marker all agree. A packaging tool may normalise it to the PEP 440
# form ``0.1.0a0``; that is the same identifier, written canonically.
__version__ = "0.1.0-alpha"
