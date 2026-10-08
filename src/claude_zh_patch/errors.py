"""Exit codes and exception types shared across the tool.

Exit codes are part of the interface: scripts and CI may rely on them.
``EXIT_UNSUPPORTED_VERSION`` is deliberately distinct so that a caller can tell
"this build is not supported" apart from "something went wrong".
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_UNSUPPORTED_VERSION = 3
EXIT_CATALOG = 4
EXIT_INCOMPATIBLE_BUNDLE = 5


class PatchError(Exception):
    """Base class for expected, user-facing failures."""

    exit_code = EXIT_ERROR

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class UnsupportedVersionError(PatchError):
    """The application bundle version is not on the installable allowlist."""

    exit_code = EXIT_UNSUPPORTED_VERSION


class CatalogError(PatchError):
    """A user-supplied language resource is missing, malformed or incomplete."""

    exit_code = EXIT_CATALOG


class IncompatibleBundleError(PatchError):
    """The bundle structure does not match what this tool knows how to patch."""

    exit_code = EXIT_INCOMPATIBLE_BUNDLE
