"""Compatibility table, integrity anchors and bundle layout constants.

The version allowlist is the primary gate. A build is installable only when its
``CFBundleShortVersionString`` appears in :data:`SUPPORTED_VERSIONS`. There is no
flag that bypasses this check -- adding a version means completing the
verification procedure in ``docs/COMPATIBILITY.md`` and committing the result.

``ANCHOR_ONLY_VERSIONS`` records builds whose static structure has been examined
but which have *not* been verified at runtime. They are listed here purely so the
tool can explain itself when it refuses; they are never installable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import __version__

TOOL_VERSION = __version__

DEFAULT_SOURCE_APP = "/Applications/Claude.app"
DEFAULT_TARGET_APP = "/Applications/Claude-3P-ZH.app"

LOCALE = "zh-Hans"
LOCALE_ALIASES = ("zh-Hans", "zh-CN")

# Bundle-relative paths.
REL_I18N = "Contents/Resources/ion-dist/i18n"
REL_ASSETS = "Contents/Resources/ion-dist/assets/v1"
REL_MARKER = "Contents/Resources/CLAUDE_ZH3P_PATCH_INFO.json"

MARKER_SCHEMA_VERSION = 1

# Minimum share of the application's base message keys that a user-supplied
# catalog must cover before an install is allowed. Below this the UI degrades to
# a half-English mix that is not useful, so the tool refuses rather than shipping
# an incomplete result.
MIN_BASE_COVERAGE = 0.70

# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------
#
# These are the exact byte sequences this tool rewrites. Every anchor must occur
# exactly the recorded number of times, in the recorded file, or the build is
# refused. Exact-count matching (rather than "at least once") is what makes an
# unknown future build fail closed instead of being silently mis-patched.

EN_ALLOWLIST = (
    '["en-US","de-DE","fr-FR","ko-KR","ja-JP","es-419","es-ES","it-IT",'
    '"hi-IN","pt-BR","id-ID"]'
)
ZH_ALLOWLIST = EN_ALLOWLIST[:-1] + ',"zh-Hans"]'

PICKER_NAME_ANCHOR = 'R={"en-US":{name:"English (United States)"'
# "简体中文" is the CLDR endonym for the zh-Hans locale, not application copy.
PICKER_NAME_PATCH = (
    'R={"zh-Hans":{name:"Chinese (Simplified)",localName:"简体中文"},'
    '"zh-CN":{name:"Chinese (Simplified)",localName:"简体中文"},'
    '"en-US":{name:"English (United States)"'
)

PICKER_OFFER_ANCHOR = "function Dz(){return x(XF,YF,YF)}"
PICKER_OFFER_PATCH = (
    'function Dz(){let e=x(XF,YF,YF);'
    'return Array.isArray(e)?[...new Set([...e,"zh-Hans"])]:e}'
)


@dataclass(frozen=True)
class Anchor:
    """One exact-match rewrite site."""

    name: str
    filename: str
    needle: str
    occurrences: int
    replacement: str


ANCHORS: tuple[Anchor, ...] = (
    Anchor(
        name="locale-allowlist",
        filename="shared-2-DgffKyBW.js",
        needle=EN_ALLOWLIST,
        occurrences=2,
        replacement=ZH_ALLOWLIST,
    ),
    Anchor(
        name="language-picker-name-map",
        filename="c49da61a8-BM3hC-jO.js",
        needle=PICKER_NAME_ANCHOR,
        occurrences=1,
        replacement=PICKER_NAME_PATCH,
    ),
    Anchor(
        name="language-picker-offer-list",
        filename="shared-25-C8tkIaeS.js",
        needle=PICKER_OFFER_ANCHOR,
        occurrences=1,
        replacement=PICKER_OFFER_PATCH,
    ),
)

# The allowlist sequence must not appear anywhere else in the asset tree; a
# second, unexpected occurrence would mean a rewrite site this tool does not
# know about.
SCAN_ALL_JS_FOR = (EN_ALLOWLIST,)
SCAN_EXPECTED_TOTAL = 2


@dataclass(frozen=True)
class VersionInfo:
    """What is known about one build."""

    cfbundleversion: str
    runtime_verified: bool
    verified_environment: str = ""
    notes: str = ""
    # sha256 of the three rewritten bundles, recorded from the reference build.
    # Hashes are structural fingerprints, not content.
    file_sha256: dict[str, str] = field(default_factory=dict)


SUPPORTED_VERSIONS: dict[str, VersionInfo] = {
    "2.26454.0": VersionInfo(
        cfbundleversion="2.26454.0",
        runtime_verified=True,
        verified_environment=(
            "macOS 26.5.2 (25F84), Apple Silicon (arm64), Claude Desktop 2.26454.0, "
            "SIP disabled, locally-created copy (no quarantine attribute)"
        ),
        notes=(
            "Reference build for v0.1.0. UI renders Simplified Chinese, language "
            "picker offers it, a third-party gateway conversation completed, and "
            "the setting survived a restart. See docs/COMPATIBILITY.md for the "
            "full list of checks that were and were not performed."
        ),
        file_sha256={
            "shared-2-DgffKyBW.js": (
                "d5e17aa1e80c60af3784988242e1c673308c5746bfdb45a1c8b449da17f6effb"
            ),
            "c49da61a8-BM3hC-jO.js": (
                "b54dfa935ab39b7a7f4de79b3a2e5a0ecb985a0ae8ad0697274e0bf903f719f6"
            ),
            "shared-25-C8tkIaeS.js": (
                "738b690f0637bc20727bfe70341307cb4712b61cdaa830c1b322f1bdbe7b5f9e"
            ),
        },
    ),
}

# Examined but NOT runtime-verified. Never installable.
ANCHOR_ONLY_VERSIONS: dict[str, str] = {
    "2.26454.2": (
        "Static inspection of the published 2.26454.2 build found the same three "
        "target files with identical sha256 digests, and every anchor matched its "
        "expected count. No runtime verification has been carried out, so this "
        "build is documented but not installable. See docs/COMPATIBILITY.md."
    ),
}

# Files that are rewritten, for reporting and integrity checks.
PATCHED_FILENAMES: tuple[str, ...] = tuple(a.filename for a in ANCHORS)
