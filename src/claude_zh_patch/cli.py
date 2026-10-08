"""Command line interface.

    check      assess a source bundle without writing anything
    apply      build a localised, re-signed copy
    verify     re-check an installed copy
    rollback   move an installed copy to the Trash
    lint       validate a language resource in detail, write nothing
    keys       list the message keys the application expects
    scan       static secret / third-party-material scan
    version    print tool and compatibility information
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from . import __version__, bundle, catalog as catalog_mod, lifecycle, patcher, security_scan
from .compat import (
    ANCHOR_ONLY_VERSIONS,
    DEFAULT_SOURCE_APP,
    DEFAULT_TARGET_APP,
    LOCALE,
    MIN_BASE_COVERAGE,
    SUPPORTED_VERSIONS,
)
from .errors import EXIT_CATALOG, EXIT_OK, EXIT_USAGE, PatchError

PROGRAM = "claude-zh-patch"


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _resolve(value: str | None, default: str) -> Path:
    return Path(value).expanduser() if value else Path(default)


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


def cmd_check(args: argparse.Namespace) -> int:
    app = _resolve(args.app, DEFAULT_SOURCE_APP)
    report = patcher.check_source(app)
    plan: patcher.PatchPlan = report["plan"]

    if args.json:
        _emit(
            {
                "source": report["path"],
                "version": report["version"],
                "identity": report["identity"],
                "supported": True,
                "rewriteTargets": list(plan.filenames),
                "entitlementsRemoved": list(plan.removed_entitlements),
                "entitlementsAdded": list(plan.added_entitlements),
            },
            True,
        )
    else:
        print(f"source           {report['path']}")
        print(f"version          {report['version']}")
        print(f"bundle id        {report['bundle_id']}")
        print(f"signing identity {report['identity']}")
        print(f"signature        {'valid' if report['signature_valid'] else 'INVALID'}")
        print(f"target locale    {LOCALE}")
        print("")
        print("structure checks all passed:")
        for name in plan.filenames:
            print(f"  rewrite  {name}")
        if plan.removed_entitlements:
            print("  strip entitlements (not valid for an ad-hoc signature):")
            for key in plan.removed_entitlements:
                print(f"    - {key}")
        for key in plan.added_entitlements:
            print(f"  add entitlement  {key}")

    if args.catalog_dir:
        loaded = catalog_mod.load_catalog(Path(args.catalog_dir).expanduser())
        english = bundle.load_english_messages(app)
        coverage = catalog_mod.compare_with_application(loaded, english)
        errors, warnings = catalog_mod.findings_for(coverage, MIN_BASE_COVERAGE)
        if args.json:
            _emit(
                {
                    "catalog": {
                        "locale": loaded.locale,
                        "displayName": loaded.display_name,
                        "license": loaded.license,
                        "origin": loaded.origin,
                        "counts": loaded.counts,
                        "coverage": coverage.line(),
                    },
                    "errors": errors,
                    "warnings": warnings,
                },
                True,
            )
        else:
            print("")
            print(f"catalog          {loaded.display_name} ({loaded.locale})")
            print(f"declared licence {loaded.license}")
            print(f"declared origin  {loaded.origin}")
            print(f"coverage         {coverage.line()}")
            for warning in warnings:
                print(f"  warning: {warning}")
            for error in errors:
                print(f"  error: {error}")
        if errors:
            return 4

    if not args.json:
        print("")
        print("Nothing was written. Structure OK -- run 'apply' to install.")
    return EXIT_OK


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def cmd_apply(args: argparse.Namespace) -> int:
    source = _resolve(args.app, DEFAULT_SOURCE_APP)
    target = _resolve(args.target, DEFAULT_TARGET_APP)

    if not args.catalog_dir:
        raise catalog_mod.CatalogError(
            "no language resource was supplied",
            detail=(
                "This project ships no translation data, so --catalog-dir is required.\n"
                "Prepare a catalog directory of your own and pass it, for example:\n"
                f"  {PROGRAM} apply --catalog-dir ~/my-catalog\n"
                "See docs/CATALOG-FORMAT.md and templates/catalog/ for the format."
            ),
        )

    loaded = catalog_mod.load_catalog(Path(args.catalog_dir).expanduser())
    result = patcher.apply(source, target, loaded)

    if args.json:
        _emit(
            {
                "target": str(result.target),
                "sourceVersion": result.plan.version,
                "rewritten": list(result.plan.filenames),
                "entitlementsRemoved": list(result.plan.removed_entitlements),
                "entitlementsAdded": list(result.plan.added_entitlements),
                "catalogCoverage": result.coverage_line,
                "excusedBranchCollapses": result.excused_branch_collapses,
                "signatureVerified": result.signing.verified,
                "warnings": list(result.warnings),
            },
            True,
        )
        return EXIT_OK

    print(f"installed        {result.target}")
    print(f"source version   {result.plan.version}")
    print(f"rewritten        {', '.join(result.plan.filenames)}")
    print(f"catalog coverage {result.coverage_line}")
    if result.plan.removed_entitlements:
        print("stripped         " + ", ".join(result.plan.removed_entitlements))
    if result.plan.added_entitlements:
        print("added            " + ", ".join(result.plan.added_entitlements))
    print("signature        deep verification passed (ad-hoc)")
    if result.excused_branch_collapses:
        print(
            f"branch collapses {result.excused_branch_collapses} message(s) omit a "
            f"plural/select branch; recorded in the install marker"
        )
    for warning in result.warnings:
        print(f"note             {warning}")

    print(
        f"""
Next steps

  1. Quit the official application before starting this copy:
       osascript -e 'quit app "Claude"'
  2. Start the localised copy:
       open -n -a {result.target}
  3. If the interface is still in English, open Settings > Language and choose
     "Chinese (Simplified)". If that entry is missing, stop and report the
     problem rather than editing configuration files.

What changed, and what did not

  * The official application was not modified. This is a separate copy.
  * Re-signing was necessary and had to be ad-hoc, because editing a bundle
    invalidates its original signature. Consequences:
      - the copy is not a Developer ID build and is not notarised;
      - 'spctl' rejects it, so a copy that arrives with a quarantine attribute
        would be blocked by Gatekeeper. A copy created locally by this tool is
        not quarantined, which is why it can start;
      - anything the official application ties to its code signature --
        notably Keychain items under its team-scoped access groups -- may behave
        differently, and some native integrations may not work.
  * Do not run both copies at the same time: they share the same user data
    directory under ~/Library/Application Support.
  * Your data, third-party gateway configuration and switch tooling are left
    untouched. See docs/DISCLAIMER.md before relying on this.
"""
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


def cmd_verify(args: argparse.Namespace) -> int:
    target = _resolve(args.target, DEFAULT_TARGET_APP)
    report = lifecycle.verify(target)

    if args.json:
        _emit(
            {
                "target": str(report.target),
                "installedVersion": report.installed_version,
                "toolVersion": report.tool_version,
                "catalog": report.catalog,
                "signatureOk": report.signature_ok,
                "gatekeeperOk": report.gatekeeper_ok,
                "localeFiles": report.locale_files,
                "catalogDigestMatches": report.digest_matches,
                "excusedBranchCollapses": report.excused_branch_collapses,
                "restrictedEntitlements": list(report.restricted_entitlements),
                "ok": report.ok,
            },
            True,
        )
    else:
        print(f"target            {report.target}")
        print(f"installed version {report.installed_version}")
        print(f"written by tool   {report.tool_version or 'unknown'}")
        print(f"catalog           {report.catalog.get('displayName', '?')} "
              f"({report.catalog.get('license', 'licence unspecified')})")
        print(f"signature         {'valid' if report.signature_ok else 'INVALID'} (ad-hoc expected)")
        print(f"gatekeeper        {'accepted' if report.gatekeeper_ok else 'rejected (expected; informational)'}")
        print(f"catalog digest    {'matches marker' if report.digest_matches else 'MISMATCH'}")
        if report.excused_branch_collapses:
            print(
                f"branch collapses {report.excused_branch_collapses} message(s) were "
                f"installed with a plural/select branch omitted"
            )
        for name, present in sorted(report.locale_files.items()):
            print(f"  {'ok ' if present else 'MISSING'} {name}")
        if report.restricted_entitlements:
            print("restricted entitlements still present (should have been stripped):")
            for key in report.restricted_entitlements:
                print(f"  - {key}")
        print("")
        print("This is a static check only. It does not prove that the application")
        print("starts, that the interface renders in the target language, or that")
        print("your gateway still works.")

    if not report.ok:
        raise PatchError("verification failed")
    return EXIT_OK


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------


def cmd_rollback(args: argparse.Namespace) -> int:
    target = _resolve(args.target, DEFAULT_TARGET_APP)
    destination = lifecycle.rollback(target)
    if args.json:
        _emit({"moved": str(target), "to": str(destination)}, True)
    else:
        print(f"moved            {target}")
        print(f"to               {destination}")
        print("")
        print("The copy was moved to the Trash, so this is reversible. The official")
        print("application and your user data were not touched.")
    return EXIT_OK


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser() if args.path else Path.cwd()
    findings = security_scan.scan_tree(root, root_label=root.name)
    errors, warnings = security_scan.summarise(findings)

    if args.json:
        _emit(
            {
                "root": str(root),
                "errors": errors,
                "warnings": warnings,
                "findings": [
                    {
                        "path": f.path,
                        "line": f.line,
                        "rule": f.rule,
                        "severity": f.severity,
                        "detail": f.detail,
                    }
                    for f in findings
                ],
            },
            True,
        )
    else:
        for finding in findings:
            print(finding.render())
        print(f"\n{errors} error(s), {warnings} warning(s) under {root}")

    return 1 if errors else EXIT_OK


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------


def _render_lint_report(
    loaded: catalog_mod.Catalog,
    coverage: catalog_mod.CoverageReport,
    errors: list[str],
    warnings: list[str],
) -> str:
    """Build the language-resource report.

    Contains message keys and format-argument names only. The application's own
    wording is never reproduced, so the report is safe to keep or share.
    """
    lines: list[str] = ["# Language resource report", ""]
    lines.append(f"- Catalogue: `{loaded.root}`")
    lines.append(f"- Locale: `{loaded.locale}` ({loaded.display_name})")
    lines.append(f"- Declared licence: {loaded.license}")
    lines.append(f"- Declared origin: {loaded.origin}")
    counts = ", ".join(f"{name} {count:,}" for name, count in loaded.counts.items())
    lines.append(f"- Messages supplied: {counts}")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append(coverage.line())
    lines.append(f"- Keys not present in this application build: {coverage.unused_keys:,}")
    lines.append("")

    defects = coverage.defects
    collapses = coverage.branch_collapses

    if defects:
        lines.append(f"## Format-argument defects ({len(defects)})")
        lines.append("")
        lines.append(
            "Each entry must render exactly the arguments shown for the application. "
            "These are refused: an invented argument throws when the message is "
            "formatted, and a dropped one leaves a visible hole. There is no flag "
            "that overrides this."
        )
        lines.append("")
        for index, mismatch in enumerate(defects, start=1):
            lines.append(f"### {index}. `{mismatch.section}[{mismatch.key}]`")
            lines.append("")
            lines.append(f"- Reason: {mismatch.reason}")
            lines.append(
                f"- Application arguments: {catalog_mod.format_arguments(mismatch.source)}"
            )
            lines.append(
                f"- Supplied arguments: {catalog_mod.format_arguments(mismatch.supplied)}"
            )
            if mismatch.required_missing:
                lines.append(
                    f"- Not rendered: {catalog_mod.format_arguments(mismatch.required_missing)}"
                )
            if mismatch.extra:
                lines.append(
                    f"- Not provided by the application: "
                    f"{catalog_mod.format_arguments(mismatch.extra)}"
                )
            lines.append(f"- Note: {mismatch.note}")
            lines.append("")
    else:
        lines.append("## Format-argument defects")
        lines.append("")
        lines.append("None. Every supplied message renders every argument the application provides.")
        lines.append("")

    if collapses:
        lines.append(f"## Branch collapses accepted ({len(collapses)})")
        lines.append("")
        lines.append(
            "These messages omit a plural or select branch the application has, and "
            "with it an argument only that branch used. A language that does not "
            "inflect writes the message that way, so these are accepted without "
            "asking you to acknowledge anything. They are listed so the acceptance is "
            "visible rather than silent."
        )
        lines.append("")
        for index, mismatch in enumerate(collapses, start=1):
            lines.append(f"### {index}. `{mismatch.section}[{mismatch.key}]`")
            lines.append("")
            lines.append(
                f"- Arguments only in removed branches: "
                f"{catalog_mod.format_arguments(mismatch.excused)}"
            )
            lines.append(
                f"- Still rendered: {catalog_mod.format_arguments(mismatch.supplied)}"
            )
            lines.append("")

    # The message findings are laid out above, so only the remaining findings go
    # here; otherwise each one would be printed twice.
    other_errors, other_warnings = catalog_mod.findings_for(
        dataclasses.replace(coverage, placeholder_mismatches=()),
        MIN_BASE_COVERAGE,
    )

    lines.append("## Other findings")
    lines.append("")
    if other_errors:
        lines.append("Blocking:")
        lines.append("")
        lines.extend(f"- {line.strip()}" for line in other_errors)
        lines.append("")
    if other_warnings:
        lines.append("Advisory:")
        lines.append("")
        lines.extend(f"- {line.strip()}" for line in other_warnings)
        lines.append("")
    if not other_errors and not other_warnings:
        lines.append("None.")
        lines.append("")

    lines.append("## Result")
    lines.append("")
    if errors:
        lines.append("**Not installable.** Fix the blocking findings above and run `lint` again.")
    else:
        lines.append(
            "**Installable.** `apply` will accept this resource"
            + (f", and will record {len(collapses)} accepted branch collapse(s)." if collapses else ".")
        )
    lines.append("")
    return "\n".join(lines)


def cmd_lint(args: argparse.Namespace) -> int:
    """Validate a language resource in detail without installing anything.

    Strict by design: this is the command used to find out what is wrong, so it
    never downgrades a finding. ``apply`` is the command that can, explicitly,
    accept a known defect.
    """
    app = _resolve(args.app, DEFAULT_SOURCE_APP)
    patcher.assert_supported_version(app)

    if not args.catalog_dir:
        raise catalog_mod.CatalogError(
            "no language resource was supplied",
            detail=(
                "lint needs --catalog-dir, pointing at the directory you prepared.\n"
                "See docs/CATALOG-FORMAT.md and templates/catalog/ for the format."
            ),
        )

    loaded = catalog_mod.load_catalog(Path(args.catalog_dir).expanduser())
    english = bundle.load_english_messages(app)
    coverage = catalog_mod.compare_with_application(loaded, english)
    errors, warnings = catalog_mod.findings_for(coverage, MIN_BASE_COVERAGE)

    text = _render_lint_report(loaded, coverage, errors, warnings)

    if args.report:
        out = Path(args.report).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"report written to {out}", file=sys.stderr)

    if args.json:
        _emit(
            {
                "catalog": str(loaded.root),
                "locale": loaded.locale,
                "counts": loaded.counts,
                "coverage": coverage.line(),
                "unusedKeys": coverage.unused_keys,
                "defects": [m.as_dict() for m in coverage.defects],
                "excusedBranchCollapses": [m.as_dict() for m in coverage.branch_collapses],
                "errors": errors,
                "warnings": warnings,
                "installable": not errors,
            },
            True,
        )
    else:
        print(text, end="")

    return EXIT_CATALOG if errors else EXIT_OK


# ---------------------------------------------------------------------------
# keys
# ---------------------------------------------------------------------------


def cmd_keys(args: argparse.Namespace) -> int:
    """Emit the message keys the application expects, with empty values.

    Only the keys are exported -- opaque identifiers, not copy. The English text
    is deliberately left behind: consult the application you already have
    installed if you need to read what a message says.
    """
    app = _resolve(args.app, DEFAULT_SOURCE_APP)
    patcher.assert_supported_version(app)

    english = bundle.load_english_messages(app)
    section = args.section
    messages = english.get(section) or {}
    if not messages:
        raise PatchError(f"the application supplies no {section!r} messages")

    payload = {key: "" for key in sorted(messages)}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if args.out:
        out = Path(args.out).expanduser()
        if out.exists() and not args.force:
            raise PatchError(
                f"{out} already exists",
                detail="Pass --force to overwrite it.",
            )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {len(payload):,} empty {section} key(s) to {out}")
    else:
        print(text, end="")

    print(
        "",
        file=sys.stderr,
    )
    print(
        f"This file contains {len(payload):,} keys and no text. It is not a usable "
        f"language resource until you fill in values you have the right to use.",
        file=sys.stderr,
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


def cmd_version(args: argparse.Namespace) -> int:
    if args.json:
        _emit(
            {
                "tool": __version__,
                "installable": sorted(SUPPORTED_VERSIONS),
                "examinedNotInstallable": sorted(ANCHOR_ONLY_VERSIONS),
            },
            True,
        )
        return EXIT_OK

    print(f"{PROGRAM} {__version__}")
    print("")
    print("installable application versions:")
    for version, info in sorted(SUPPORTED_VERSIONS.items()):
        marker = "runtime-verified" if info.runtime_verified else "NOT runtime-verified"
        print(f"  {version}  ({marker})")
        if info.verified_environment:
            print(f"      verified on: {info.verified_environment}")
    print("")
    if ANCHOR_ONLY_VERSIONS:
        print("examined but not installable:")
        for version in sorted(ANCHOR_ONLY_VERSIONS):
            print(f"  {version}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=(
            "Install a Simplified Chinese interface into a local copy of Claude "
            "Desktop. Unofficial; not affiliated with Anthropic."
        ),
        epilog=(
            "This tool ships no translation data. 'apply' needs --catalog-dir "
            "pointing at a language resource you prepared yourself."
        ),
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    check = subparsers.add_parser("check", help="assess a source bundle, write nothing")
    check.add_argument("--app", help=f"source bundle (default: {DEFAULT_SOURCE_APP})")
    check.add_argument("--catalog-dir", help="also validate this language resource")
    check.set_defaults(handler=cmd_check)

    apply_parser = subparsers.add_parser("apply", help="create the localised copy")
    apply_parser.add_argument("--app", help=f"source bundle (default: {DEFAULT_SOURCE_APP})")
    apply_parser.add_argument("--target", help=f"output copy (default: {DEFAULT_TARGET_APP})")
    apply_parser.add_argument(
        "--catalog-dir",
        help="directory holding the language resource you prepared (required)",
    )
    apply_parser.set_defaults(handler=cmd_apply)

    verify = subparsers.add_parser("verify", help="re-check an installed copy")
    verify.add_argument("--target", help=f"installed copy (default: {DEFAULT_TARGET_APP})")
    verify.set_defaults(handler=cmd_verify)

    rollback = subparsers.add_parser("rollback", help="move an installed copy to the Trash")
    rollback.add_argument("--target", help=f"installed copy (default: {DEFAULT_TARGET_APP})")
    rollback.set_defaults(handler=cmd_rollback)

    scan = subparsers.add_parser("scan", help="static secret and material scan")
    scan.add_argument("path", nargs="?", help="directory to scan (default: current directory)")
    scan.set_defaults(handler=cmd_scan)

    lint = subparsers.add_parser(
        "lint",
        help="validate a language resource in detail, writing nothing",
        description=(
            "Reports every problem in a language resource, strictly. Unlike apply, "
            "lint never downgrades a finding, so it is the command to run while "
            "fixing a resource."
        ),
    )
    lint.add_argument("--app", help=f"source bundle (default: {DEFAULT_SOURCE_APP})")
    lint.add_argument("--catalog-dir", help="the language resource to validate")
    lint.add_argument("--report", help="also write a detailed report to this path")
    lint.set_defaults(handler=cmd_lint)

    keys = subparsers.add_parser(
        "keys", help="list the message keys the application expects, with empty values"
    )
    keys.add_argument("--app", help=f"source bundle (default: {DEFAULT_SOURCE_APP})")
    keys.add_argument("--section", choices=("base", "dynamic"), default="base")
    keys.add_argument("--out", help="write to this file instead of stdout")
    keys.add_argument("--force", action="store_true", help="overwrite --out if it exists")
    keys.set_defaults(handler=cmd_keys)

    version = subparsers.add_parser("version", help="tool and compatibility information")
    version.set_defaults(handler=cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE

    try:
        return args.handler(args)
    except PatchError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        if exc.detail:
            print("", file=sys.stderr)
            print(exc.detail, file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:  # pragma: no cover
        print("interrupted", file=sys.stderr)
        return 130


__all__ = ["build_parser", "main"]
