"""Ad-hoc re-signing of a patched copy, with restricted entitlements removed.

Why this module exists
----------------------
Editing a bundle's JavaScript breaks the signature seal over its resources, so a
patched copy must be re-signed. Without a Developer ID certificate the only
available identity is ad-hoc (``codesign --sign -``).

Ad-hoc signing cannot carry *restricted* entitlements. An entitlement is
restricted when the system honours it only for code whose identity is backed by a
provisioning profile issued to a registered team:

* ``com.apple.application-identifier``
* ``com.apple.developer.team-identifier``
* anything under ``com.apple.developer.`` (provisioning-profile capabilities)
* ``keychain-access-groups`` (team-prefixed keychain groups)

Re-signing ad-hoc while *preserving* those values -- what
``codesign --preserve-metadata=entitlements`` does -- yields a bundle that claims
an identity it cannot prove. At best the values are inert; in practice they make
the copy fail to launch, or fail keychain access, in ways that are tedious to
diagnose. They were issued to Anthropic and are useless to anyone else regardless.

This module strips them and adds the one entitlement an ad-hoc signed Electron
application actually needs: ``com.apple.security.cs.disable-library-validation``,
which lets a process with no team identity load its own nested, separately signed
frameworks.

The remaining ``com.apple.security.*`` entitlements (camera, microphone, USB,
virtualization, JIT, …) are ordinary hardened-runtime entitlements. They are kept
because the application uses them and they survive ad-hoc signing.

Nested code is signed inside-out: deepest item first, enclosing bundle last.
Apple deprecates ``--deep`` for *signing* precisely because it applies one set of
options to every nested item; that is the mistake this module avoids.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import PatchError

CODESIGN = "/usr/bin/codesign"

#: Entitlements an ad-hoc signature cannot legitimately carry.
RESTRICTED_KEYS = frozenset(
    {
        "com.apple.application-identifier",
        "com.apple.developer.team-identifier",
        "keychain-access-groups",
    }
)
RESTRICTED_PREFIXES = ("com.apple.developer.",)

#: Added to the outer bundle so it can load its own nested frameworks.
ADHOC_REQUIRED_ENTITLEMENTS: dict[str, object] = {
    "com.apple.security.cs.disable-library-validation": True,
}

MACHO_MAGICS = (
    b"\xcf\xfa\xed\xfe",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xfe\xed\xfa\xce",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf",
    b"\xbf\xba\xfe\xca",
)

BUNDLE_SUFFIXES = (".app", ".framework", ".xpc")
SKIP_DIR_NAMES = frozenset({"_CodeSignature", "CodeResources", "__pycache__"})


class SigningError(PatchError):
    pass


@dataclass(frozen=True)
class SigningReport:
    signed_items: tuple[str, ...]
    stripped_from: tuple[str, ...]
    removed_keys: tuple[str, ...]
    added_keys: tuple[str, ...]
    verified: bool
    verify_detail: str


def read_entitlements(item: Path) -> dict[str, object] | None:
    """Return the entitlements of ``item``, or ``None`` if it carries none."""
    result = subprocess.run(
        [CODESIGN, "-d", "--entitlements", ":-", str(item)],
        capture_output=True,
    )
    blob = result.stdout.strip() or result.stderr.strip()
    if not blob or not blob.startswith(b"<?xml") and not blob.startswith(b"bplist"):
        return None
    try:
        data = plistlib.loads(blob)
    except Exception:  # noqa: BLE001 - a malformed entitlement blob is "no entitlements"
        return None
    return data if isinstance(data, dict) else None


def is_restricted(key: str) -> bool:
    return key in RESTRICTED_KEYS or key.startswith(RESTRICTED_PREFIXES)


def strip_restricted(entitlements: dict[str, object]) -> tuple[dict[str, object], list[str]]:
    """Split ``entitlements`` into what may be kept ad-hoc and what must go."""
    kept: dict[str, object] = {}
    removed: list[str] = []
    for key, value in entitlements.items():
        if is_restricted(key):
            removed.append(key)
        else:
            kept[key] = value
    return kept, sorted(removed)


def plan_main_entitlements(entitlements: dict[str, object] | None) -> tuple[dict[str, object], list[str], list[str]]:
    """Work out the entitlement set for the outer bundle.

    Returns ``(final, removed, added)`` so callers can report the difference
    without performing it.
    """
    kept, removed = strip_restricted(entitlements or {})
    added = []
    for key, value in ADHOC_REQUIRED_ENTITLEMENTS.items():
        if kept.get(key) != value:
            kept[key] = value
            added.append(key)
    return kept, removed, sorted(added)


def _is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) in MACHO_MAGICS
    except OSError:
        return False


def collect_signables(app: Path) -> list[Path]:
    """Nested code items to re-sign, deepest first.

    Mach-O files living inside a nested bundle are omitted: signing that bundle
    covers them, and signing the file first would be overwritten one step later.
    """
    app = Path(app)
    found: list[Path] = []
    for path in app.rglob("*"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            if path.is_dir():
                if path.suffix in BUNDLE_SUFFIXES:
                    found.append(path)
            elif path.is_file() and _is_macho(path):
                found.append(path)
        except OSError:
            continue

    bundles = [p for p in found if p.is_dir()]

    def inside_nested_bundle(path: Path) -> bool:
        return any(path != bundle and bundle in path.parents for bundle in bundles)

    items = [p for p in found if p.is_dir() or not inside_nested_bundle(p)]
    items.sort(key=lambda p: len(p.parts), reverse=True)
    return items


def _sign(path: Path, entitlements: dict[str, object] | None) -> None:
    args = [
        CODESIGN,
        "--force",
        "--sign",
        "-",
        "--options",
        "runtime",
        "--timestamp=none",
    ]
    tmp_path: str | None = None
    try:
        if entitlements:
            handle = tempfile.NamedTemporaryFile(
                "wb", suffix=".plist", delete=False, prefix="zh-patch-ent-"
            )
            try:
                handle.write(plistlib.dumps(entitlements, fmt=plistlib.FMT_XML))
            finally:
                handle.close()
            tmp_path = handle.name
            args += ["--entitlements", tmp_path]
        args.append(str(path))
        result = subprocess.run(args, capture_output=True)
        if result.returncode:
            detail = result.stderr.decode("utf-8", "replace").strip()[-2000:]
            raise SigningError(f"codesign failed for {path}", detail=detail)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def resign_adhoc(app: Path) -> SigningReport:
    """Re-sign ``app`` ad-hoc, inside-out, stripping restricted entitlements.

    The outer bundle receives :func:`plan_main_entitlements`; nested items keep
    their own entitlements minus anything restricted.
    """
    app = Path(app)
    if not app.is_dir():
        raise SigningError(f"not a directory: {app}")

    signed: list[str] = []
    stripped_from: list[str] = []
    removed_keys: set[str] = set()

    for item in collect_signables(app):
        entitlements = read_entitlements(item)
        if entitlements is None:
            _sign(item, None)
        else:
            kept, removed = strip_restricted(entitlements)
            if removed:
                stripped_from.append(str(item.relative_to(app)))
                removed_keys.update(removed)
            _sign(item, kept)
        signed.append(str(item.relative_to(app)))

    main_kept, main_removed, added = plan_main_entitlements(read_entitlements(app))
    if main_removed:
        stripped_from.append(".")
        removed_keys.update(main_removed)
    _sign(app, main_kept)
    signed.append(".")

    ok, detail = verify(app)
    return SigningReport(
        signed_items=tuple(signed),
        stripped_from=tuple(stripped_from),
        removed_keys=tuple(sorted(removed_keys)),
        added_keys=tuple(added),
        verified=ok,
        verify_detail=detail,
    )


def verify(app: Path) -> tuple[bool, str]:
    result = subprocess.run(
        [CODESIGN, "--verify", "--deep", "--strict", str(app)],
        capture_output=True,
    )
    return result.returncode == 0, result.stderr.decode("utf-8", "replace").strip()


def gatekeeper_assessment(app: Path) -> tuple[bool, str]:
    """Run ``spctl``. Informational only -- see docs/DISCLAIMER.md.

    A locally created copy is not quarantined, so Gatekeeper does not normally
    block it at launch even when this reports a rejection.
    """
    result = subprocess.run(
        ["/usr/sbin/spctl", "-a", "-vvv", "-t", "exec", str(app)],
        capture_output=True,
    )
    detail = (result.stdout + result.stderr).decode("utf-8", "replace").strip()
    return result.returncode == 0, detail
