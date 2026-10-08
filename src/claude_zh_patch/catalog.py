"""Loading and validating user-supplied language resources.

This project ships no translation data and contains no extraction or download
logic. A *catalog* is a directory the user prepares and is responsible for having
the right to use. The manifest records what the user declares about it, so that
the declaration appears in the install report instead of being assumed.

Layout expected by :func:`load_catalog`::

    <catalog-dir>/
      catalog.json          manifest, required
      <any .json files the manifest points at>

Manifest format (schema version 1)::

    {
      "schemaVersion": 1,
      "locale": "zh-Hans",
      "displayName": "...",
      "license": "CC-BY-SA-4.0",
      "origin": "self-authored | employer-supplied | <url>",
      "files": {
        "base": "base.json",
        "dynamic": "dynamic.json",
        "overrides": "overrides.json"
      }
    }

Only ``files.base`` is required. ``dynamic`` and ``overrides`` are optional and
fall back to empty.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import icu
from .compat import LOCALE_ALIASES
from .errors import CatalogError

MANIFEST_NAME = "catalog.json"
SCHEMA_VERSION = 1
SECTIONS = ("base", "dynamic", "overrides")
_REQUIRED_SECTIONS = ("base",)

# Cap on how many problems are quoted back before summarising, so a badly broken
# catalog produces a readable error rather than thousands of lines.
_MAX_REPORTED = 20


@dataclass(frozen=True)
class Catalog:
    """A validated user-supplied language resource."""

    root: Path
    locale: str
    display_name: str
    license: str
    origin: str
    sections: dict[str, dict[str, str]]

    @property
    def base(self) -> dict[str, str]:
        return self.sections["base"]

    @property
    def counts(self) -> dict[str, int]:
        return {name: len(messages) for name, messages in self.sections.items()}


@dataclass(frozen=True)
class PlaceholderMismatch:
    """One message whose format arguments differ from the application's.

    Describes *arguments*, never text: the application's own wording is not
    reproduced anywhere in this tool's output.

    ``excused`` holds the dropped arguments that disappeared because the
    translation removed the branches using them, which is how a language that
    does not inflect for plural legitimately writes the message. Everything else
    is a defect and blocks the install; there is no flag that overrides it.
    """

    section: str
    key: str
    source: tuple[str, ...]
    supplied: tuple[str, ...]
    excused: tuple[str, ...] = ()
    parse_error: str = ""

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.source) - set(self.supplied)))

    @property
    def extra(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.supplied) - set(self.source)))

    @property
    def required_missing(self) -> tuple[str, ...]:
        """Dropped arguments that are *not* explained by a removed branch."""
        return tuple(name for name in self.missing if name not in self.excused)

    @property
    def is_defect(self) -> bool:
        """True when this difference will be visible in the interface."""
        return bool(self.parse_error or self.extra or self.required_missing)

    @property
    def reason(self) -> str:
        if self.parse_error:
            return f"cannot be parsed: {self.parse_error}"
        if self.extra:
            return "uses a format argument the application's message does not provide"
        if self.required_missing:
            return "drops a format argument the application's message provides"
        return "drops a branch, and with it an argument only that branch used"

    @property
    def note(self) -> str:
        if self.is_defect:
            if self.excused:
                return (
                    "Some of the dropped arguments are explained by a removed branch, "
                    "but the ones listed above are not: the application renders them "
                    "outside every branch, or inside a branch the translation kept."
                )
            return "An argument the application provides is not rendered at all."
        return (
            "Every dropped argument was used only by a branch the translation removed. "
            "Removing branches is how a language that does not inflect for plural "
            "writes this message, so this is accepted automatically."
        )

    def render(self) -> str:
        lines = [
            f"{self.section}[{self.key}]  {self.reason}",
            f"    application: {format_arguments(self.source)}",
            f"    supplied:    {format_arguments(self.supplied)}",
        ]
        if self.excused:
            lines.append(f"    excused:     {format_arguments(self.excused)}")
        if self.note:
            lines.append(f"    note: {self.note}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, object]:
        return {
            "section": self.section,
            "key": self.key,
            "reason": self.reason,
            "isDefect": self.is_defect,
            "applicationArguments": list(self.source),
            "suppliedArguments": list(self.supplied),
            "missing": list(self.missing),
            "extra": list(self.extra),
            "requiredMissing": list(self.required_missing),
            "excused": list(self.excused),
            "note": self.note,
        }


def format_arguments(names: tuple[str, ...]) -> str:
    """Render an argument-name set for humans, distinguishing "none" from empty."""
    if not names:
        return "(none)"
    return ", ".join(f"{{{name}}}" for name in names)


@dataclass(frozen=True)
class CoverageReport:
    """How a catalog lines up with the application's own English messages."""

    totals: dict[str, int]
    covered: dict[str, int]
    unused_keys: int
    placeholder_mismatches: tuple[PlaceholderMismatch, ...]

    @property
    def defects(self) -> tuple[PlaceholderMismatch, ...]:
        """Differences that the user will see. These block an install."""
        return tuple(m for m in self.placeholder_mismatches if m.is_defect)

    @property
    def branch_collapses(self) -> tuple[PlaceholderMismatch, ...]:
        """Differences fully explained by removed branches. Accepted automatically."""
        return tuple(m for m in self.placeholder_mismatches if not m.is_defect)

    @property
    def base_ratio(self) -> float:
        total = self.totals.get("base", 0)
        if total == 0:
            return 0.0
        return self.covered.get("base", 0) / total

    def line(self) -> str:
        parts = []
        for name in SECTIONS:
            total = self.totals.get(name, 0)
            if total == 0:
                continue
            got = self.covered.get(name, 0)
            parts.append(f"{name}: {got:,}/{total:,} ({got * 100 / total:.1f}%)")
        return "; ".join(parts) if parts else "no comparable messages"


def load_catalog(root: Path) -> Catalog:
    """Read and validate a catalog directory.

    Raises :class:`CatalogError` with an actionable message on any problem. Every
    message value is checked for ICU well-formedness; ``base`` must be present
    and non-empty.
    """
    root = Path(root)
    if not root.is_dir():
        raise CatalogError(f"catalog directory not found: {root}")

    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise CatalogError(
            f"missing manifest: {manifest_path}",
            detail=(
                "A catalog directory must contain catalog.json. See "
                "docs/CATALOG-FORMAT.md, and templates/catalog/ for a starting point."
            ),
        )
    manifest = _read_json_object(manifest_path)

    version = manifest.get("schemaVersion")
    if version != SCHEMA_VERSION:
        raise CatalogError(
            f"{MANIFEST_NAME}: unsupported schemaVersion {version!r} "
            f"(this tool implements {SCHEMA_VERSION})"
        )

    locale = manifest.get("locale")
    if locale not in LOCALE_ALIASES:
        raise CatalogError(
            f"{MANIFEST_NAME}: locale {locale!r} is not supported "
            f"(expected one of {', '.join(LOCALE_ALIASES)})"
        )

    files = manifest.get("files")
    if not isinstance(files, dict):
        raise CatalogError(f"{MANIFEST_NAME}: 'files' must be an object")

    sections: dict[str, dict[str, str]] = {}
    for name in SECTIONS:
        ref = files.get(name)
        if ref is None:
            if name in _REQUIRED_SECTIONS:
                raise CatalogError(f"{MANIFEST_NAME}: 'files.{name}' is required")
            sections[name] = {}
            continue
        if not isinstance(ref, str) or not ref:
            raise CatalogError(f"{MANIFEST_NAME}: 'files.{name}' must be a file name")
        sections[name] = _read_messages(root, ref, name)

    if not sections["base"]:
        raise CatalogError(
            f"catalog section 'base' is empty ({files.get('base')!r})",
            detail="An empty catalog would install an interface with no translated text.",
        )

    return Catalog(
        root=root,
        locale=locale,
        display_name=str(manifest.get("displayName") or locale),
        license=str(manifest.get("license") or "unspecified"),
        origin=str(manifest.get("origin") or "unspecified"),
        sections=sections,
    )


def _read_json_object(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise CatalogError(f"{path}: top level must be a JSON object")
    return raw


def _read_messages(root: Path, ref: str, section: str) -> dict[str, str]:
    if Path(ref).is_absolute() or ".." in Path(ref).parts:
        raise CatalogError(
            f"{MANIFEST_NAME}: 'files.{section}' must be a relative path inside the "
            f"catalog directory, got {ref!r}"
        )
    path = root / ref
    if not path.is_file():
        raise CatalogError(f"missing catalog file referenced by manifest: {path}")

    raw = _read_json_object(path)
    problems: list[str] = []
    messages: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            problems.append(f"{path.name}: key {key!r} is not a string")
            continue
        if not isinstance(value, str):
            problems.append(
                f"{path.name}: [{key}] is {type(value).__name__}, expected a string"
            )
            continue
        try:
            icu.validate_pattern(value, context=f"{path.name}[{key}]")
        except icu.ICUError as exc:
            problems.append(str(exc))
            continue
        messages[key] = value

    if problems:
        raise CatalogError(
            f"{path}: {len(problems)} message(s) rejected",
            detail=_summarise(problems),
        )
    return messages


def _summarise(problems: list[str]) -> str:
    shown = problems[:_MAX_REPORTED]
    lines = list(shown)
    if len(problems) > len(shown):
        lines.append(f"... and {len(problems) - len(shown)} more")
    return "\n".join(lines)


def compare_with_application(
    catalog: Catalog,
    english: dict[str, dict[str, str]],
) -> CoverageReport:
    """Compare a catalog against the application's own English messages.

    Two things are checked per section:

    * how many of the application's keys the catalog covers;
    * whether the catalog keeps exactly the same format arguments as the English
      message for every key it does supply. A dropped or invented placeholder is
      a rendering bug, so mismatches are reported by key.
    """
    totals: dict[str, int] = {}
    covered: dict[str, int] = {}
    mismatches: list[PlaceholderMismatch] = []
    unused = 0

    for name in SECTIONS:
        source = english.get(name) or {}
        supplied = catalog.sections.get(name) or {}
        totals[name] = len(source)
        covered[name] = len(source.keys() & supplied.keys())
        unused += len(supplied.keys() - source.keys())

        for key in sorted(source.keys() & supplied.keys()):
            try:
                want = icu.argument_profile(source[key], context=f"en-US[{key}]")
                got = icu.argument_profile(supplied[key], context=f"{catalog.locale}[{key}]")
            except icu.ICUError as exc:  # pragma: no cover - source messages are trusted
                mismatches.append(
                    PlaceholderMismatch(
                        section=name, key=key, source=(), supplied=(), parse_error=str(exc)
                    )
                )
                continue
            if want.all != got.all:
                dropped = want.all - got.all
                excused = tuple(
                    sorted(
                        name for name in dropped if icu.is_branch_collapse(want, got, name)
                    )
                )
                mismatches.append(
                    PlaceholderMismatch(
                        section=name,
                        key=key,
                        source=tuple(sorted(want.all)),
                        supplied=tuple(sorted(got.all)),
                        excused=excused,
                    )
                )

    return CoverageReport(
        totals=totals,
        covered=covered,
        unused_keys=unused,
        placeholder_mismatches=tuple(mismatches),
    )


def findings_for(
    report: CoverageReport,
    minimum_ratio: float,
) -> tuple[list[str], list[str]]:
    """Split a coverage report into blocking errors and advisory warnings.

    A difference between a translation and the application's arguments blocks the
    install whenever the user would see it: an invented argument (which throws at
    render time) or a dropped argument the application renders outside a
    conditional branch, or inside one the translation kept.

    A difference explained entirely by removed branches does not block. That is a
    language choosing not to inflect, not a mistake, so it is accepted without
    asking the user to acknowledge anything. There is deliberately no flag that
    overrides the blocking cases.
    """
    errors: list[str] = []
    warnings: list[str] = []

    defects = report.defects
    if defects:
        errors.append(
            f"{len(defects)} message(s) rejected: the supplied text does not render "
            f"every format argument the application provides for that message"
        )
        for mismatch in defects[:_MAX_REPORTED]:
            errors.extend("  " + line for line in mismatch.render().splitlines())
        if len(defects) > _MAX_REPORTED:
            errors.append(f"  ... and {len(defects) - _MAX_REPORTED} more")

    collapses = report.branch_collapses
    if collapses:
        keys = ", ".join(f"{m.section}[{m.key}]" for m in collapses[:8])
        if len(collapses) > 8:
            keys += f", and {len(collapses) - 8} more"
        warnings.append(
            f"{len(collapses)} message(s) remove a plural or select branch and with it "
            f"an argument only that branch used; accepted, because a language that "
            f"does not inflect writes the message that way ({keys})"
        )

    if report.base_ratio < minimum_ratio:
        errors.append(
            f"base coverage is {report.base_ratio * 100:.1f}%, below the required "
            f"{minimum_ratio * 100:.0f}%"
        )

    if report.unused_keys:
        warnings.append(
            f"{report.unused_keys} catalog key(s) do not exist in this application "
            f"build and will be written but never used"
        )
    if report.totals.get("base", 0) and not report.totals.get("dynamic", 0):
        warnings.append("the application has dynamic messages but the catalog supplies none")

    return errors, warnings
