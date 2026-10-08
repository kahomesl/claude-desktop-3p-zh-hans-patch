"""Building the patch plan and producing a patched copy.

The plan is computed and fully validated *before* anything is written, so a
refusal leaves the filesystem untouched. The source application is only ever
read; output goes to a separate bundle that must not already exist.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import bundle, signing
from .catalog import Catalog, compare_with_application, findings_for
from .compat import (
    ANCHORS,
    ANCHOR_ONLY_VERSIONS,
    LOCALE,
    LOCALE_ALIASES,
    MARKER_SCHEMA_VERSION,
    MIN_BASE_COVERAGE,
    PATCHED_FILENAMES,
    REL_ASSETS,
    REL_I18N,
    REL_MARKER,
    SCAN_ALL_JS_FOR,
    SCAN_EXPECTED_TOTAL,
    SUPPORTED_VERSIONS,
    TOOL_VERSION,
    VersionInfo,
)
from .errors import CatalogError, IncompatibleBundleError, PatchError, UnsupportedVersionError
from .signing import SigningError, SigningReport

SECTIONS = ("base", "dynamic", "overrides")

#: Written by this tool; proves a bundle is our output, never used as an input.
MARKER_PATCH_ID = "claude-zh3p-zh-Hans"


@dataclass(frozen=True)
class PatchPlan:
    app: Path
    version: str
    rewrites: dict[Path, str]
    removed_entitlements: tuple[str, ...]
    added_entitlements: tuple[str, ...]

    @property
    def filenames(self) -> tuple[str, ...]:
        return tuple(sorted(path.name for path in self.rewrites))


@dataclass(frozen=True)
class ApplyResult:
    target: Path
    plan: PatchPlan
    signing: SigningReport
    catalog_digest: str
    coverage_line: str
    warnings: tuple[str, ...] = field(default=())
    excused_branch_collapses: int = 0


def assert_supported_version(app: Path) -> VersionInfo:
    """Return the compatibility record, or refuse with exit code 3.

    There is deliberately no override flag. Supporting a new build means running
    the checks in ``docs/COMPATIBILITY.md`` and committing the result.
    """
    version = bundle.read_version(app)
    info = SUPPORTED_VERSIONS.get(version)
    if info is not None:
        return info

    lines = [f"Claude Desktop {version or '<unknown>'} is not a supported version."]
    examined = ANCHOR_ONLY_VERSIONS.get(version)
    if examined:
        lines.append("")
        lines.append(f"Note on {version}: {examined}")
    else:
        lines.append("")
        lines.append(
            "Only these builds are installable: "
            + ", ".join(sorted(SUPPORTED_VERSIONS))
        )
    lines.append("")
    lines.append(
        "There is no flag that bypasses this check. If you are on an unsupported "
        "build you can still install from a copy of a supported one: see the "
        "'Installing from a backup' section of docs/INSTALL.md."
    )
    raise UnsupportedVersionError("\n".join(lines))


def build_plan(app: Path) -> PatchPlan:
    """Validate every rewrite site and return the exact text to write.

    Any deviation -- a missing file, a different occurrence count, an unexpected
    copy of the allowlist elsewhere in the asset tree, or a digest mismatch --
    refuses the build rather than guessing.
    """
    info = assert_supported_version(app)

    assets = Path(app) / REL_ASSETS
    if not assets.is_dir():
        raise IncompatibleBundleError(f"missing asset directory: {assets}")

    if bundle.has_locale(app, LOCALE) or bundle.has_locale(app, "zh-CN"):
        raise IncompatibleBundleError(
            "this bundle already carries a zh-Hans catalog; it looks like it has "
            "already been patched. Patch a pristine copy instead."
        )

    rewrites: dict[Path, str] = {}
    for anchor in ANCHORS:
        path = assets / anchor.filename
        if not path.is_file():
            raise IncompatibleBundleError(
                f"expected file is missing: {anchor.filename}",
                detail=(
                    "This tool only understands one exact build layout. Do not "
                    "point it at a different release."
                ),
            )
        text = path.read_text(encoding="utf-8")
        found = text.count(anchor.needle)
        if found != anchor.occurrences:
            raise IncompatibleBundleError(
                f"anchor {anchor.name!r} occurs {found} time(s) in "
                f"{anchor.filename}, expected exactly {anchor.occurrences}",
                detail="Refusing to patch a build whose structure differs from the reference.",
            )
        rewrites[path] = text.replace(anchor.needle, anchor.replacement)

    stray = bundle.scan_for_stray_anchors(app, SCAN_ALL_JS_FOR)
    if stray != SCAN_EXPECTED_TOTAL:
        raise IncompatibleBundleError(
            f"the locale allowlist appears {stray} time(s) across the asset tree, "
            f"expected exactly {SCAN_EXPECTED_TOTAL}",
            detail=(
                "An extra occurrence would be a rewrite site this tool does not "
                "know about, so the build is refused."
            ),
        )

    for filename, expected in info.file_sha256.items():
        actual = bundle.file_sha256(assets / filename)
        if actual != expected:
            raise IncompatibleBundleError(
                f"digest mismatch for {filename}",
                detail=f"recorded {expected}\nfound    {actual}",
            )

    removed, added = signing.plan_main_entitlements(signing.read_entitlements(app))[1:]
    return PatchPlan(
        app=Path(app),
        version=info.cfbundleversion,
        rewrites=rewrites,
        removed_entitlements=tuple(removed),
        added_entitlements=tuple(added),
    )


def check_source(app: Path) -> dict[str, object]:
    """Read-only assessment used by the ``check`` command.

    Raises :class:`UnsupportedVersionError` (exit code 3) for a build that is not
    installable, so ``check && apply`` behaves correctly in a script.
    """
    app = Path(app)
    info = bundle.read_bundle_info(app)
    plan = build_plan(app)  # refuses unsupported versions and structure drift
    return {
        "path": str(app),
        "version": info.version,
        "bundle_id": info.bundle_id,
        "identity": info.signed_identity,
        "signature_valid": info.signature_valid,
        "plan": plan,
    }


def _ditto(source: Path, target: Path) -> None:
    result = subprocess.run(
        ["/usr/bin/ditto", str(source), str(target)], capture_output=True
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()[-2000:]
        raise PatchError(f"could not copy {source} to {target}", detail=detail)


def _put_text(path: Path, text: str) -> None:
    """Atomically replace ``path``, keeping its permission bits."""
    mode = path.stat().st_mode
    temp = path.with_name(path.name + ".zh-patch-tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


def _write_catalogs(target: Path, catalog: Catalog) -> None:
    root = Path(target) / REL_I18N
    for locale in LOCALE_ALIASES:
        for section, relative in (
            ("base", f"{locale}.json"),
            ("dynamic", f"dynamic/{locale}.json"),
            ("overrides", f"{locale}.overrides.json"),
        ):
            out = root / relative
            out.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(
                catalog.sections.get(section, {}),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            out.write_text(payload + "\n", encoding="utf-8")


def catalog_digest(sections: dict[str, dict[str, str]]) -> str:
    """A fingerprint of the catalog as installed, recorded in the marker."""
    digest = hashlib.sha256()
    for name in SECTIONS:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        payload = json.dumps(
            sections.get(name, {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        digest.update(payload.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _write_marker(
    target: Path,
    info: VersionInfo,
    catalog: Catalog,
    plan: PatchPlan,
    digest: str,
    excused_branch_collapses: int,
) -> None:
    # No absolute paths and no account data: this file is sealed into the bundle
    # and may be shared when reporting a problem.
    marker = {
        "schemaVersion": MARKER_SCHEMA_VERSION,
        "patch": MARKER_PATCH_ID,
        "toolVersion": TOOL_VERSION,
        "sourceVersion": info.cfbundleversion,
        "locale": LOCALE,
        "catalog": {
            "displayName": catalog.display_name,
            "license": catalog.license,
            "origin": catalog.origin,
            "counts": catalog.counts,
            "digest": digest,
            # Messages that omit a plural/select branch the application has and
            # therefore omit an argument only that branch used. Recorded so that
            # `verify` can report what was accepted, not to allow anything: a
            # difference the user would actually see is refused outright.
            "excusedBranchCollapses": excused_branch_collapses,
        },
        "patchedFiles": list(plan.filenames),
        "entitlements": {
            "removed": list(plan.removed_entitlements),
            "added": list(plan.added_entitlements),
        },
    }
    path = Path(target) / REL_MARKER
    path.write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def apply(
    source: Path,
    target: Path,
    catalog: Catalog,
    *,
    sign=None,
) -> ApplyResult:
    """Copy ``source`` to ``target``, localize it, re-sign it and verify."""
    source = Path(source)
    target = Path(target)
    signer = sign or signing.resign_adhoc

    if source.resolve() == target.resolve():
        raise PatchError("refusing to patch in place: source and target are the same path")
    if target.exists():
        raise PatchError(
            f"target already exists: {target}",
            detail="Refusing to overwrite. Remove it first, or pass a different --target.",
        )

    info = assert_supported_version(source)

    ok, detail = bundle.verify_signature(source)
    if not ok:
        raise IncompatibleBundleError(
            f"the source bundle's signature does not verify: {source}",
            detail=detail[-2000:] or "(no detail)",
        )

    english = bundle.load_english_messages(source)
    if not english.get("base"):
        raise IncompatibleBundleError(
            "could not read the application's own en-US messages",
            detail=(
                f"Expected a message catalog under "
                f"{Path(source) / REL_I18N}. Without it a supplied catalog cannot "
                f"be checked, so the install is refused."
            ),
        )
    coverage = compare_with_application(catalog, english)
    errors, warnings = findings_for(coverage, MIN_BASE_COVERAGE)
    if errors:
        raise CatalogError(
            "the supplied catalog cannot be installed:\n" + "\n".join(errors)
        )
    excused = len(coverage.branch_collapses)

    plan = build_plan(source)

    created = False
    try:
        _ditto(source, target)
        created = True

        for absolute, text in plan.rewrites.items():
            _put_text(target / absolute.relative_to(source), text)

        _write_catalogs(target, catalog)
        digest = catalog_digest(catalog.sections)
        _write_marker(target, info, catalog, plan, digest, excused)

        report = signer(target)
        if not report.verified:
            raise SigningError(
                "the patched copy failed signature verification",
                detail=report.verify_detail[-2000:],
            )
    except BaseException:
        # We created this path, so a partial copy is ours to remove. The source
        # bundle is never touched.
        if created:
            shutil.rmtree(target, ignore_errors=True)
        raise

    return ApplyResult(
        target=target,
        plan=plan,
        signing=report,
        catalog_digest=digest,
        coverage_line=coverage.line(),
        warnings=tuple(warnings),
        excused_branch_collapses=excused,
    )


__all__ = [
    "ApplyResult",
    "PatchPlan",
    "apply",
    "assert_supported_version",
    "build_plan",
    "catalog_digest",
    "check_source",
]
