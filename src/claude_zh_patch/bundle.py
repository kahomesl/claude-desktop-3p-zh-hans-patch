"""Read-only inspection of an application bundle.

Nothing in this module writes to the bundle. It answers questions the rest of the
tool needs to decide whether an install is safe: what version is this, is its
signature intact, does it already carry this locale, and what are the exact bytes
at each anchor site.
"""

from __future__ import annotations

import hashlib
import json
import plistlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .compat import REL_ASSETS, REL_I18N, REL_MARKER, Anchor
from .errors import IncompatibleBundleError

CODESIGN = "/usr/bin/codesign"


@dataclass(frozen=True)
class BundleInfo:
    path: Path
    version: str
    bundle_id: str
    team_identifier: str
    is_adhoc: bool
    signature_valid: bool
    signature_detail: str

    @property
    def signed_identity(self) -> str:
        if self.is_adhoc:
            return "ad-hoc"
        return self.team_identifier or "unknown"


def _info_plist(app: Path) -> dict:
    app = Path(app)
    if not app.is_dir():
        raise IncompatibleBundleError(f"application bundle not found: {app}")
    path = app / "Contents/Info.plist"
    if not path.is_file():
        raise IncompatibleBundleError(f"not an application bundle (no Info.plist): {app}")
    try:
        return plistlib.loads(path.read_bytes())
    except Exception as exc:  # noqa: BLE001 - surface any plist failure verbatim
        raise IncompatibleBundleError(f"cannot read {path}: {exc}") from exc


def read_version(app: Path) -> str:
    """Return ``CFBundleShortVersionString``."""
    return str(_info_plist(Path(app)).get("CFBundleShortVersionString", ""))


def read_bundle_id(app: Path) -> str:
    return str(_info_plist(Path(app)).get("CFBundleIdentifier", ""))


def codesign_details(bundle: Path) -> dict[str, str]:
    """Parse ``codesign -dv`` output into a flat mapping.

    Keys include ``Identifier``, ``TeamIdentifier``, ``Signature``, ``Authority``.
    """
    result = subprocess.run(
        [CODESIGN, "-dv", "--verbose=4", str(bundle)],
        capture_output=True,
    )
    details: dict[str, str] = {}
    for line in result.stderr.decode("utf-8", "replace").splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in details:
            details[key] = value.strip()
    return details


def verify_signature(bundle: Path) -> tuple[bool, str]:
    """Run a strict deep verification. Returns ``(ok, detail)``."""
    result = subprocess.run(
        [CODESIGN, "--verify", "--deep", "--strict", str(bundle)],
        capture_output=True,
    )
    detail = result.stderr.decode("utf-8", "replace").strip()
    return result.returncode == 0, detail


def read_bundle_info(app: Path) -> BundleInfo:
    app = Path(app)
    if not app.is_dir():
        raise IncompatibleBundleError(f"application bundle not found: {app}")
    details = codesign_details(app)
    ok, detail = verify_signature(app)
    return BundleInfo(
        path=app,
        version=read_version(app),
        bundle_id=read_bundle_id(app),
        team_identifier=details.get("TeamIdentifier", ""),
        is_adhoc=details.get("Signature", "").lower() == "adhoc" or bool(details.get("adhoc")),
        signature_valid=ok,
        signature_detail=detail,
    )


def asset_dir(app: Path) -> Path:
    return Path(app) / REL_ASSETS


def i18n_dir(app: Path) -> Path:
    return Path(app) / REL_I18N


def marker_path(app: Path) -> Path:
    return Path(app) / REL_MARKER


def has_marker(app: Path) -> bool:
    """True when this bundle was produced by this tool."""
    path = marker_path(app)
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("patch") == "claude-zh3p-zh-Hans"


def has_locale(app: Path, locale: str) -> bool:
    return (i18n_dir(app) / f"{locale}.json").is_file()


def count_anchor(text: str, anchor: Anchor) -> int:
    return text.count(anchor.needle)


def scan_for_stray_anchors(app: Path, needles: tuple[str, ...]) -> int:
    """Count occurrences of ``needles`` across every ``*.js`` in the asset tree.

    An occurrence outside a known anchor site would mean a rewrite point this
    tool does not understand, so the caller compares the total against the sum of
    the anchors' expected counts.
    """
    total = 0
    root = asset_dir(app)
    if not root.is_dir():
        raise IncompatibleBundleError(f"missing asset directory: {root}")
    for path in root.glob("*.js"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for needle in needles:
            total += text.count(needle)
    return total


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_english_messages(app: Path) -> dict[str, dict[str, str]]:
    """Read the application's own ``en-US`` messages, used only to compare shapes.

    These are never copied into any output of this tool.
    """
    root = i18n_dir(app)
    messages: dict[str, dict[str, str]] = {}
    for section, relative in (
        ("base", "en-US.json"),
        ("dynamic", "dynamic/en-US.json"),
        ("overrides", "en-US.overrides.json"),
    ):
        path = root / relative
        if not path.is_file():
            messages[section] = {}
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IncompatibleBundleError(f"cannot read {path}: {exc}") from exc
        messages[section] = {
            k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)
        } if isinstance(data, dict) else {}
    return messages
