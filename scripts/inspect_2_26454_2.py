#!/usr/bin/env python3
"""Read-only preflight for Claude Desktop 2.26454.2.

This checks an untouched signed source against the three exact fingerprinted
rewrite targets. No application file or user profile is modified. The command
performs ONLY static checks; any previously recorded runtime verification is
separately documented in docs/COMPATIBILITY.md.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from claude_zh_patch import bundle, catalog as catalog_mod, compat  # noqa: E402
from claude_zh_patch.errors import PatchError  # noqa: E402

CANDIDATE = "2.26454.2"
REFERENCE = "2.26454.0"
EXPECTED_BUNDLE_ID = "com.anthropic.claudefordesktop"


class PreflightError(Exception):
    def __init__(self, message: str, code: int = 5):
        super().__init__(message)
        self.code = code


def inspect_app(
    app: Path,
    catalog_dir: Path | None = None,
    *,
    node_executable: str | None = None,
) -> dict[str, object]:
    """Read source bundle and return structural evidence; never write to it."""
    app = Path(app).expanduser()

    try:
        version = bundle.read_version(app)
    except PatchError as exc:
        raise PreflightError(str(exc)) from exc

    if version != CANDIDATE:
        raise PreflightError(
            f"Expected the official {CANDIDATE} candidate, found {version!r}. "
            "The public installer still refuses this version.",
            code=3,
        )

    if bundle.read_bundle_id(app) != EXPECTED_BUNDLE_ID:
        raise PreflightError("Unexpected bundle identifier; not an official Claude Desktop bundle.")

    signature_valid, signature_detail = bundle.verify_signature(app)
    if not signature_valid:
        raise PreflightError(
            "Original application code signature is invalid: "
            + (signature_detail[-400:] or "(no diagnostic)")
        )

    if bundle.has_locale(app, compat.LOCALE) or bundle.has_locale(app, "zh-CN"):
        raise PreflightError("Source already contains a Chinese catalog; use an untouched signed app.")

    reference = compat.SUPPORTED_VERSIONS[REFERENCE]
    expected = reference.file_sha256
    assets = bundle.asset_dir(app)
    if not assets.is_dir():
        raise PreflightError("Missing JavaScript asset directory.")

    if set(expected) != set(compat.PATCHED_FILENAMES):
        raise PreflightError("Repository reference fingerprint table is incomplete.")

    fingerprints: dict[str, str] = {}
    patched: dict[str, str] = {}
    for anchor in compat.ANCHORS:
        source = assets / anchor.filename
        if not source.is_file():
            raise PreflightError(f"Missing rewrite target: {anchor.filename}")
        raw = source.read_text(encoding="utf-8")
        occurrences = raw.count(anchor.needle)
        if occurrences != anchor.occurrences:
            raise PreflightError(
                f"Anchor {anchor.name}: found {occurrences}, expected {anchor.occurrences}."
            )
        if anchor.filename in patched:
            # Multiple rewrite sites in one JS file need cumulative replacement.
            patched[anchor.filename] = patched[anchor.filename].replace(
                anchor.needle, anchor.replacement
            )
        else:
            patched[anchor.filename] = raw.replace(anchor.needle, anchor.replacement)

    for filename, digest in expected.items():
        actual = bundle.file_sha256(assets / filename)
        if actual != digest:
            raise PreflightError(
                f"SHA-256 mismatch in {filename}. Candidate differs from the examined build."
            )
        fingerprints[filename] = actual

    stray_count = bundle.scan_for_stray_anchors(app, compat.SCAN_ALL_JS_FOR)
    if stray_count != compat.SCAN_EXPECTED_TOTAL:
        raise PreflightError(
            f"Unknown allowlist occurrences: {stray_count}, expected {compat.SCAN_EXPECTED_TOTAL}."
        )

    node = node_executable or shutil.which("node")
    if not node:
        raise PreflightError(
            "Node.js is required for the JavaScript syntax preflight; no write was made."
        )
    for name, source in sorted(patched.items()):
        proc = subprocess.run(
            [node, "--input-type=module", "--check"],
            input=source,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode:
            raise PreflightError(
                f"Rewritten {name} failed JavaScript syntax validation: "
                + proc.stderr[-400:]
            )

    english = bundle.load_english_messages(app)
    if not english.get("base") or not english.get("dynamic"):
        raise PreflightError("Reference English base/dynamic catalogs are incomplete.")

    supported = compat.SUPPORTED_VERSIONS.get(CANDIDATE)
    report: dict[str, object] = {
        "candidate": CANDIDATE,
        "status": "STATIC_PASS",
        "runtimeVerificationPerformedByThisCommand": False,
        "runtimeEvidenceRecorded": bool(supported and supported.runtime_verified),
        "installable": supported is not None,
        "signatureValid": True,
        "bundleId": EXPECTED_BUNDLE_ID,
        "matchedAnchors": len(compat.ANCHORS),
        "wholeTreeAllowlistOccurrences": stray_count,
        "fileSha256": fingerprints,
        "javascriptSyntax": "PASS",
        "englishCounts": {section: len(values) for section, values in english.items()},
        "catalogChecked": catalog_dir is not None,
    }

    if catalog_dir is not None:
        loaded = catalog_mod.load_catalog(Path(catalog_dir).expanduser())
        coverage = catalog_mod.compare_with_application(loaded, english)
        errors, warnings = catalog_mod.findings_for(coverage, compat.MIN_BASE_COVERAGE)
        report["catalogCoverage"] = coverage.line()
        report["catalogErrors"] = errors
        report["catalogWarnings"] = warnings
        report["excusedBranchCollapses"] = len(coverage.branch_collapses)
        if errors:
            raise PreflightError(
                f"Catalog failed strict validation ({len(errors)} blocking finding(s)).",
                code=4,
            )

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="READ ONLY: inspect an official Claude Desktop 2.26454.2 source bundle."
    )
    parser.add_argument("--app", default="/Applications/Claude.app")
    parser.add_argument("--catalog-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = inspect_app(Path(args.app), args.catalog_dir)
    except (PreflightError, PatchError, OSError, UnicodeError) as exc:
        code = getattr(exc, "code", getattr(exc, "exit_code", 5))
        print(f"PRECHECK FAILED: {exc}", file=sys.stderr)
        return code

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"STRUCTURAL PASS: official Claude Desktop {CANDIDATE}")
        print(f"Matched {report['matchedAnchors']} anchor locations; JS syntax: PASS")
        print(f"English catalog counts: {report['englishCounts']}")
        if args.catalog_dir:
            print(f"Catalog coverage: {report['catalogCoverage']}")
            print(f"Accepted conditional branch collapses: {report['excusedBranchCollapses']}")
        print("THIS COMMAND IS STATIC ONLY; no runtime launch performed here.")
        print(f"Previously recorded runtime evidence: {report['runtimeEvidenceRecorded']}")
        print(f"Included in exact-version installable allowlist: {report['installable']}")
        print("See docs/COMPATIBILITY.md for verified environment and limitations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
