"""Verifying and rolling back an installed copy.

Verification is static: it proves the bundle on disk is the one this tool wrote
and that it is internally consistent. It cannot prove the application launches or
that the interface renders in the target language, and it says so.
"""

from __future__ import annotations

import json
import plistlib
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from . import bundle, signing
from .compat import (
    LOCALE,
    LOCALE_ALIASES,
    MARKER_SCHEMA_VERSION,
    REL_I18N,
    SUPPORTED_VERSIONS,
)
from .errors import PatchError
from .patcher import MARKER_PATCH_ID, catalog_digest

SECTIONS = ("base", "dynamic", "overrides")


@dataclass(frozen=True)
class VerifyReport:
    target: Path
    installed_version: str
    tool_version: str
    catalog: dict
    signature_ok: bool
    signature_detail: str
    gatekeeper_ok: bool
    gatekeeper_detail: str
    locale_files: dict[str, bool]
    digest_matches: bool
    restricted_entitlements: tuple[str, ...]

    @property
    def excused_branch_collapses(self) -> int:
        """Messages installed with a plural/select branch omitted, per the marker."""
        value = self.catalog.get("excusedBranchCollapses") or 0
        return int(value) if isinstance(value, (int, float, str)) else 0

    @property
    def ok(self) -> bool:
        return (
            self.signature_ok
            and self.digest_matches
            and all(self.locale_files.values())
            and not self.restricted_entitlements
        )


def read_marker(target: Path) -> dict:
    path = bundle.marker_path(target)
    if not path.is_file():
        raise PatchError(
            f"no install marker in {target}",
            detail=(
                "This bundle was not produced by this tool. Refusing to treat it as "
                "an installed copy."
            ),
        )
    try:
        marker = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PatchError(f"cannot read {path}: {exc}") from exc
    if marker.get("patch") != MARKER_PATCH_ID:
        raise PatchError(f"{path} does not identify this patch")
    if marker.get("schemaVersion") != MARKER_SCHEMA_VERSION:
        raise PatchError(
            f"{path}: marker schema {marker.get('schemaVersion')!r} is not supported "
            f"by this tool ({MARKER_SCHEMA_VERSION})"
        )
    return marker


def _installed_sections(target: Path) -> dict[str, dict[str, str]]:
    root = Path(target) / REL_I18N
    sections: dict[str, dict[str, str]] = {name: {} for name in SECTIONS}
    for section, relative in (
        ("base", f"{LOCALE}.json"),
        ("dynamic", f"dynamic/{LOCALE}.json"),
        ("overrides", f"{LOCALE}.overrides.json"),
    ):
        path = root / relative
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            sections[section] = {
                k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)
            }
    return sections


def verify(target: Path) -> VerifyReport:
    target = Path(target)
    if not target.is_dir():
        raise PatchError(f"not found: {target}")

    marker = read_marker(target)

    version = bundle.read_version(target)
    expected = marker.get("sourceVersion")
    if expected and version != expected:
        raise PatchError(
            f"installed copy reports version {version}, marker says {expected}"
        )

    signature_ok, signature_detail = signing.verify(target)
    gatekeeper_ok, gatekeeper_detail = signing.gatekeeper_assessment(target)

    locale_files = {
        relative: (Path(target) / REL_I18N / relative).is_file()
        for relative in (
            f"{LOCALE}.json",
            f"dynamic/{LOCALE}.json",
            f"{LOCALE}.overrides.json",
        )
    }
    for alias in LOCALE_ALIASES:
        locale_files[f"{alias}.json"] = (Path(target) / REL_I18N / f"{alias}.json").is_file()

    digest_matches = catalog_digest(_installed_sections(target)) == marker.get(
        "catalog", {}
    ).get("digest")

    entitlements = signing.read_entitlements(target) or {}
    restricted = tuple(sorted(key for key in entitlements if signing.is_restricted(key)))

    return VerifyReport(
        target=target,
        installed_version=version,
        tool_version=str(marker.get("toolVersion", "")),
        catalog=dict(marker.get("catalog", {})),
        signature_ok=signature_ok,
        signature_detail=signature_detail,
        gatekeeper_ok=gatekeeper_ok,
        gatekeeper_detail=gatekeeper_detail,
        locale_files=locale_files,
        digest_matches=digest_matches,
        restricted_entitlements=restricted,
    )


def read_target_entitlements(target: Path) -> dict:
    """Convenience for reporting: the entitlement set of an installed copy."""
    return signing.read_entitlements(target) or {}


def rollback(target: Path, *, trash: Path | None = None) -> Path:
    """Move an installed copy to the Trash. Returns the new location.

    Refuses unless the bundle carries this tool's marker, so the official
    application and user backups cannot be removed by mistake. Nothing is
    deleted: the bundle is moved to the Trash, which is reversible.

    ``trash`` overrides the destination and exists so the test suite never
    touches a real user's Trash. User data under ``~/Library/Application
    Support`` is never touched either way.
    """
    target = Path(target)
    if not target.is_dir():
        raise PatchError(f"not found: {target}")
    if target.suffix != ".app":
        raise PatchError(f"refusing to roll back something that is not an .app: {target}")

    read_marker(target)

    destination_root = Path(trash) if trash is not None else Path.home() / ".Trash"
    destination_root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    destination = destination_root / f"{target.name}.rolled-back-{stamp}"
    counter = 1
    while destination.exists():
        destination = destination_root / f"{target.name}.rolled-back-{stamp}-{counter}"
        counter += 1

    shutil.move(str(target), str(destination))
    return destination


__all__ = [
    "VerifyReport",
    "read_marker",
    "read_target_entitlements",
    "rollback",
    "verify",
]
