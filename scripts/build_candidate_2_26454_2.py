#!/usr/bin/env python3
"""Isolated runtime-test build for the *exact* Claude Desktop 2.26454.2.

TEST-ONLY on this draft adaptation branch, not part of the released installer.
The public CLI still refuses this version. The script requires a successful
read-only preflight and an explicit, unused target path before any write.

No original application, existing localized copy, or Claude-3p profile is changed.
The operator must verify launching and usage on macOS separately.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from claude_zh_patch import catalog as catalog_mod  # noqa: E402
from claude_zh_patch import compat, lifecycle, patcher  # noqa: E402
from claude_zh_patch.errors import PatchError  # noqa: E402
from scripts import inspect_2_26454_2 as preflight  # noqa: E402

CANDIDATE = preflight.CANDIDATE
REFERENCE = preflight.REFERENCE
EXPECTED_TARGET_NAME = "Claude-3P-ZH-2.26454.2.app"


class CandidateBuildError(Exception):
    pass


def validate_target(source: Path, target: Path) -> None:
    """Refuse overwrite, confusing names, and locations near user data."""
    source = source.expanduser().resolve()
    target = target.expanduser()
    if target.name != EXPECTED_TARGET_NAME or target.suffix != ".app":
        raise CandidateBuildError(
            "Candidate target must be an independent application named "
            + EXPECTED_TARGET_NAME
        )

    if target.exists() or target.is_symlink():
        raise CandidateBuildError("Target already exists; refusing to overwrite it.")

    resolved = target.resolve()
    protected = {
        source,
        Path("/Applications/Claude.app").resolve(),
        Path("/Applications/Claude-3P-ZH.app").resolve(),
    }
    if resolved in protected:
        raise CandidateBuildError("Refusing to replace an official or working application.")

    user_data = (Path.home() / "Library/Application Support").resolve()
    if user_data == resolved or user_data in resolved.parents:
        raise CandidateBuildError("Refusing to write inside the user data directory.")

    if not target.parent.is_dir():
        raise CandidateBuildError(
            f"Parent directory does not exist: {target.parent}"
        )


@contextlib.contextmanager
def _temporarily_register_exact_candidate():
    """Allow just the preflighted candidate inside this test process.

    No shipped source, CLI allowlist, or version-gate switch is modified.
    The entry cannot survive a process exit or escape this context.
    """
    if CANDIDATE in compat.SUPPORTED_VERSIONS:
        raise CandidateBuildError(
            "Candidate is already in the installable table; this test-only "
            "builder should not be used after promotion."
        )
    ref = compat.SUPPORTED_VERSIONS[REFERENCE]
    info = compat.VersionInfo(
        cfbundleversion=CANDIDATE,
        runtime_verified=False,
        notes="Temporary candidate entry for isolated local runtime test only.",
        file_sha256=dict(ref.file_sha256),
    )
    compat.SUPPORTED_VERSIONS[CANDIDATE] = info
    try:
        yield
    finally:
        compat.SUPPORTED_VERSIONS.pop(CANDIDATE, None)


def build_candidate(
    source: Path, target: Path, catalog_dir: Path
) -> dict[str, object]:
    """Preflight, patch independent copy, re-sign, statically verify.

    Runtime launch / Gateway / persistence MUST still be checked manually.
    """
    source = Path(source).expanduser()
    target = Path(target).expanduser()
    catalog_dir = Path(catalog_dir).expanduser()
    validate_target(source, target)

    if not (catalog_dir / "catalog.json").is_file():
        raise CandidateBuildError(
            f"No catalog.json at {catalog_dir}; supply a catalog you are "
            "authorized to use. No translation data is included."
        )

    # This checks the official signature, exact binary fingerprints, anchors,
    # JS syntax and the strict ICU/coverage policy before writing anything.
    static = preflight.inspect_app(source, catalog_dir)
    if not static.get("signatureValid") or static.get("javascriptSyntax") != "PASS":
        raise CandidateBuildError("Candidate static preflight did not pass.")

    loaded = catalog_mod.load_catalog(catalog_dir)

    with _temporarily_register_exact_candidate():
        result = patcher.apply(source, target, loaded)

    verify = lifecycle.verify(target)
    if not verify.ok:
        raise CandidateBuildError(
            "Candidate was created, but its post-install verification failed. "
            "Do not launch this copy. Inspect or roll back ONLY this new target."
        )

    return {
        "candidate": CANDIDATE,
        "target": str(target),
        "status": "BUILT_STATICALLY_VERIFIED_RUNTIME_UNTESTED",
        "signatureValid": verify.signature_ok,
        "catalogIntegrity": verify.digest_matches,
        "gatekeeperAssessmentPassed": verify.gatekeeper_ok,
        "conditionalBranchCollapses": result.excused_branch_collapses,
        "runtimeVerified": False,
        "officialInstallerAllowlistChanged": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Draft-only candidate test build for Claude Desktop 2.26454.2. "
            "Does not install over an existing app or modify official source."
        )
    )
    parser.add_argument("--app", default="/Applications/Claude.app")
    parser.add_argument("--catalog-dir", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args(argv)

    try:
        report = build_candidate(
            Path(args.app), Path(args.target), Path(args.catalog_dir)
        )
    except (CandidateBuildError, preflight.PreflightError, PatchError, OSError) as exc:
        code = getattr(exc, "code", getattr(exc, "exit_code", 5))
        print(f"CANDIDATE BUILD FAILED: {exc}", file=sys.stderr)
        return code

    print("===== CANDIDATE BUILD PASS (STATIC ONLY) =====")
    for key, value in report.items():
        print(f"{key}: {value}")
    print("NEXT: Completely quit other Claude instances before a manual launch.")
    print("Do not merge this draft branch or announce runtime support yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
