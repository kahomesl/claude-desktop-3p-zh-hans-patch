"""Minimal ICU MessageFormat validator and argument analyser.

User-supplied catalogs are evaluated by the application's own message formatter
at render time. A malformed pattern therefore shows up as a crash inside the UI,
long after install, with no obvious link back to the catalog. Validating up front
turns that into a clear install-time error naming the offending key.

Beyond validity, this module answers *where* each format argument is used. That
question decides whether a translation is defective or merely idiomatic, and it
cannot be answered by matching substrings:

* An argument used outside every branch is rendered unconditionally. Losing it
  leaves a hole in the interface, always a defect.
* An argument used only inside a ``plural``/``select`` branch disappears when
  that branch is removed. Removing branches is how a language that does not
  inflect for plural writes the message, so losing such an argument is only a
  defect if the branch survived.

:func:`is_branch_collapse` implements that second rule exactly, by recording the
path of ``(selector argument, label)`` pairs each argument sits under.

This is a validator, not a formatter. It is deliberately lenient in two places:

* apostrophe handling follows the "optional" convention, so a lone ``'`` is
  treated as a literal rather than an error;
* unknown *style* text (everything after the second comma of a
  ``number``/``date``/``time`` argument) is not interpreted.

Rejecting a catalog the application would have rendered is worse than accepting
one it would not, so both choices favour the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


class ICUError(ValueError):
    """Raised when a pattern is not a well-formed ICU MessageFormat message."""


PLURAL_TYPES = frozenset({"plural", "selectordinal"})
SELECT_TYPES = frozenset({"select"})
SIMPLE_TYPES = frozenset(
    {"number", "date", "time", "duration", "spellout", "ordinal", "choice", "list"}
)
VALID_TYPES = PLURAL_TYPES | SELECT_TYPES | SIMPLE_TYPES

PLURAL_KEYWORDS = frozenset({"zero", "one", "two", "few", "many", "other"})

_IDENT_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "_-$."
)
_WHITESPACE = " \t\r\n"

#: A path is the chain of ``(selector argument, label)`` pairs an argument sits
#: inside, outermost first. An empty path means the argument is used outside
#: every conditional branch.
Path = tuple[tuple[str, str], ...]


def validate_pattern(pattern: str, *, context: str = "") -> None:
    """Raise :class:`ICUError` if ``pattern`` is not a well-formed ICU message."""
    if not isinstance(pattern, str):
        raise ICUError(_err(context, "message is not a string"))
    _analyse(pattern, context)


def argument_names(pattern: str, *, context: str = "") -> frozenset[str]:
    """Return every argument name referenced by ``pattern``."""
    return argument_profile(pattern, context=context).all


@dataclass(frozen=True)
class ArgumentProfile:
    """Which arguments a message uses, and where.

    ``conditional`` holds the arguments that appear only inside a
    ``plural``/``select`` branch. ``selectors`` maps each argument used as a
    branch selector to the labels present at that node, and ``occurrences`` maps
    each argument to the paths at which it is used. Together these allow a
    precise answer to "was this argument dropped because a branch was removed?".
    """

    all: frozenset[str]
    conditional: frozenset[str]
    selectors: Mapping[str, frozenset[str]] = field(default_factory=dict)
    occurrences: Mapping[str, tuple[Path, ...]] = field(default_factory=dict)

    @property
    def unconditional(self) -> frozenset[str]:
        """Arguments used outside every conditional branch."""
        return self.all - self.conditional


def argument_profile(pattern: str, *, context: str = "") -> ArgumentProfile:
    """Return every argument name in ``pattern``, with where each one appears."""
    collector = _Collector()
    _message(pattern, 0, len(pattern), 0, (), collector, context)
    return ArgumentProfile(
        all=frozenset(collector.names),
        conditional=frozenset(collector.conditional),
        selectors={name: frozenset(labels) for name, labels in collector.selectors.items()},
        occurrences={
            name: tuple(paths) for name, paths in collector.occurrences.items()
        },
    )


def is_branch_collapse(
    source: ArgumentProfile, translation: ArgumentProfile, name: str
) -> bool:
    """Was ``name`` dropped because the translation removed every branch using it?

    True only when each use of ``name`` in the source sits somewhere under a
    branch whose label the translation no longer offers. An argument that the
    translation still has a branch for is *not* excused, so dropping it from a
    retained branch is reported as the defect it is.
    """
    paths = source.occurrences.get(name)
    if not paths:
        return False
    for path in paths:
        if not any(
            label not in translation.selectors.get(selector, frozenset())
            for selector, label in path
        ):
            return False
    return True


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


class _Collector:
    """Mutable accumulator threaded through the parse."""

    __slots__ = ("names", "conditional", "selectors", "occurrences")

    def __init__(self) -> None:
        self.names: set[str] = set()
        self.conditional: set[str] = set()
        self.selectors: dict[str, set[str]] = {}
        self.occurrences: dict[str, list[Path]] = {}

    def argument(self, name: str, path: Path) -> None:
        self.names.add(name)
        if path:
            self.conditional.add(name)
        self.occurrences.setdefault(name, []).append(path)

    def selector(self, name: str, label: str) -> None:
        self.selectors.setdefault(name, set()).add(label)


def _err(context: str, message: str) -> str:
    return f"{context}: {message}" if context else message


def _analyse(text: str, ctx: str) -> _Collector:
    collector = _Collector()
    _message(text, 0, len(text), 0, (), collector, ctx)
    return collector


def _message(
    text: str, i: int, end: int, depth: int, path: Path, collector: _Collector, ctx: str
) -> int:
    """Consume a message body; return the index just past it.

    At ``depth == 0`` the message runs to ``end``. Inside a branch it stops at the
    closing brace, which the caller consumes.
    """
    while i < end:
        ch = text[i]
        if ch == "'":
            i = _apostrophe(text, i, end)
        elif ch == "}":
            if depth == 0:
                raise ICUError(_err(ctx, f"unmatched '}}' at offset {i}"))
            return i
        elif ch == "{":
            i = _argument(text, i, end, path, collector, ctx)
        else:
            i += 1
    if depth != 0:
        raise ICUError(_err(ctx, f"unterminated argument (message ends at offset {end})"))
    return i


def _apostrophe(text: str, i: int, end: int) -> int:
    """Consume an apostrophe run starting at ``i``; return the next index."""
    nxt = text[i + 1] if i + 1 < end else ""
    if nxt == "'":
        return i + 2  # '' is a literal apostrophe
    if nxt in ("{", "}"):
        j = i + 1
        while j < end:
            if text[j] == "'":
                if j + 1 < end and text[j + 1] == "'":
                    j += 2
                    continue
                return j + 1
            j += 1
        return end  # unterminated quote: ICU renders the remainder literally
    return i + 1  # a bare apostrophe is a literal


def _argument(
    text: str, i: int, end: int, path: Path, collector: _Collector, ctx: str
) -> int:
    """Consume one ``{...}`` argument starting at ``i``."""
    j = _skip_ws(text, i + 1, end)
    if j >= end:
        raise ICUError(_err(ctx, f"unterminated argument at offset {i}"))
    if text[j] == "}":
        raise ICUError(_err(ctx, f"empty argument at offset {i}"))

    name, j = _identifier(text, j, end, ctx)
    collector.argument(name, path)

    j = _skip_ws(text, j, end)
    if j >= end:
        raise ICUError(_err(ctx, f"unterminated argument at offset {i}"))
    if text[j] == "}":
        return j + 1
    if text[j] != ",":
        raise ICUError(_err(ctx, f"expected ',' or '}}' after argument name at offset {j}"))

    j = _skip_ws(text, j + 1, end)
    if j >= end:
        raise ICUError(_err(ctx, f"unterminated argument at offset {i}"))
    argtype, j = _identifier(text, j, end, ctx)
    if argtype not in VALID_TYPES:
        raise ICUError(_err(ctx, f"unsupported argument type {argtype!r} at offset {j}"))

    j = _skip_ws(text, j, end)
    if j >= end:
        raise ICUError(_err(ctx, f"unterminated argument at offset {i}"))
    if text[j] == "}":
        return j + 1
    if text[j] != ",":
        raise ICUError(_err(ctx, f"expected ',' or '}}' after argument type at offset {j}"))

    if argtype in PLURAL_TYPES or argtype in SELECT_TYPES:
        return _choices(text, j + 1, end, path, collector, ctx, argtype, name, i)
    return _literal_style(text, j + 1, end, ctx, i)


def _choices(
    text: str,
    i: int,
    end: int,
    path: Path,
    collector: _Collector,
    ctx: str,
    argtype: str,
    selector_argument: str,
    arg_start: int,
) -> int:
    """Consume ``label {branch}`` pairs up to the closing brace."""
    branches = 0
    has_other = False
    j = i
    while True:
        j = _skip_ws(text, j, end)
        if j >= end:
            raise ICUError(_err(ctx, f"unterminated {argtype} at offset {arg_start}"))
        if text[j] == "}":
            break

        start = j
        while j < end and text[j] != "{":
            j += 1
        if j >= end:
            raise ICUError(_err(ctx, f"unterminated {argtype} selector at offset {start}"))

        label = text[start:j].strip()
        if not label:
            raise ICUError(_err(ctx, f"empty {argtype} selector at offset {start}"))
        _check_selector(label, argtype, ctx, start)
        collector.selector(selector_argument, label)
        if label == "other":
            has_other = True
        branches += 1

        branch_path = path + ((selector_argument, label),)
        j = _message(text, j + 1, end, 1, branch_path, collector, ctx) + 1

    if branches == 0:
        raise ICUError(_err(ctx, f"{argtype} has no branches at offset {arg_start}"))
    if not has_other:
        raise ICUError(
            _err(ctx, f"{argtype} is missing the required 'other' branch at offset {arg_start}")
        )
    return j + 1


def _check_selector(label: str, argtype: str, ctx: str, offset: int) -> None:
    if argtype not in PLURAL_TYPES:
        return  # any non-empty label is a valid select label
    if label in PLURAL_KEYWORDS:
        return
    if label.startswith("=") and label[1:].lstrip("-").isdigit():
        return
    raise ICUError(_err(ctx, f"invalid plural selector {label!r} at offset {offset}"))


def _literal_style(text: str, i: int, end: int, ctx: str, arg_start: int) -> int:
    """Skip an opaque style body (``::`` skeletons, date formats) to the close."""
    j = i
    while j < end:
        ch = text[j]
        if ch == "'":
            j = _apostrophe(text, j, end)
        elif ch == "}":
            return j + 1
        elif ch == "{":
            raise ICUError(_err(ctx, f"unexpected '{{' in style at offset {j}"))
        else:
            j += 1
    raise ICUError(_err(ctx, f"unterminated argument at offset {arg_start}"))


def _identifier(text: str, i: int, end: int, ctx: str) -> tuple[str, int]:
    start = i
    while i < end and text[i] in _IDENT_CHARS:
        i += 1
    if i == start:
        raise ICUError(_err(ctx, f"expected an identifier at offset {start}"))
    return text[start:i], i


def _skip_ws(text: str, i: int, end: int) -> int:
    while i < end and text[i] in _WHITESPACE:
        i += 1
    return i
