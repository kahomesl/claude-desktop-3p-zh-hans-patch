"""Static scan for secrets, personal data and material that must not be shipped.

Run before every commit and in CI. It looks for two different classes of problem:

* **Credentials and personal data** -- API keys, tokens, private keys, session
  cookies, home-directory paths, e-mail addresses, chat transcripts.
* **Third-party application material** -- anything that would mean redistributing
  someone else's code or content: app bundles, Electron archives, provisioning
  profiles, modified JavaScript, or an extracted translation catalog.

Findings never echo the matched value; only its length and a short masked prefix,
so running the scanner cannot itself leak a secret into a log.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

#: Add this token to a line to suppress findings on it.
ALLOW_MARKER = "security-scan:allow"

SKIP_DIR_NAMES = frozenset(
    {".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "node_modules"}
)

#: Files larger than this are scanned only for path rules.
MAX_TEXT_BYTES = 8 << 20

_TEXT_SUFFIXES = frozenset(
    {
        ".py", ".md", ".json", ".txt", ".yml", ".yaml", ".toml", ".cfg", ".ini",
        ".sh", ".bash", ".zsh", ".js", ".mjs", ".ts", ".html", ".css", ".xml",
        ".plist", ".entitlements", ".gitignore", ".gitattributes", ".editorconfig",
        ".example", ".sample", ".tmpl", "",
    }
)

# (rule name, compiled pattern, severity)
CONTENT_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("anthropic-api-key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{24,}"), SEVERITY_ERROR),
    ("openai-api-key", re.compile(r"\bsk-(?!ant-)[A-Za-z0-9]{32,}"), SEVERITY_ERROR),
    ("github-token", re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}"), SEVERITY_ERROR),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), SEVERITY_ERROR),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), SEVERITY_ERROR),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), SEVERITY_ERROR),
    ("stripe-key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}"), SEVERITY_ERROR),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), SEVERITY_ERROR),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), SEVERITY_ERROR),
    (
        "bearer-token",
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{24,}"),
        SEVERITY_ERROR,
    ),
    (
        "assigned-secret",
        re.compile(
            r"""(?ix)
            \b(?:api[_-]?key|apikey|secret|client[_-]?secret|access[_-]?token|
                 refresh[_-]?token|auth[_-]?token|password|passwd|passphrase|
                 private[_-]?key|session[_-]?id|cookie)\b
            \s*[:=]\s*
            ["']([^"'\s]{12,})["']
            """
        ),
        SEVERITY_ERROR,
    ),
    (
        "cookie-header",
        re.compile(r"(?i)\b(?:set-)?cookie\s*:\s*\S{20,}"),
        SEVERITY_WARNING,
    ),
    (
        "home-directory-path",
        re.compile(r"/Users/[A-Za-z0-9._\-]+"),
        SEVERITY_ERROR,
    ),
    (
        "email-address",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        SEVERITY_WARNING,
    ),
    (
        "chat-transcript",
        re.compile(r'"role"\s*:\s*"(?:user|assistant|system)"'),
        SEVERITY_WARNING,
    ),
)

#: Values that match the patterns above but are not secrets.
EMAIL_ALLOW = re.compile(
    r"@(?:example\.(?:com|org|net)|localhost|users\.noreply\.github\.com|"
    r"anthropic\.com|github\.com)$",
    re.IGNORECASE,
)

# Path-shaped rules: name fragments that must never be committed.
FORBIDDEN_PATH_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("app-bundle", re.compile(r"\.app$", re.IGNORECASE), SEVERITY_ERROR),
    ("electron-archive", re.compile(r"\.asar$", re.IGNORECASE), SEVERITY_ERROR),
    (
        "provisioning-profile",
        re.compile(r"\.(?:mobileprovision|provisionprofile)$", re.IGNORECASE),
        SEVERITY_ERROR,
    ),
    ("key-material", re.compile(r"\.(?:p12|pfx|key|keystore|jks)$", re.IGNORECASE), SEVERITY_ERROR),
    ("certificate", re.compile(r"\.(?:cer|crt|der)$", re.IGNORECASE), SEVERITY_WARNING),
    ("binary-library", re.compile(r"\.(?:dylib|so|node)$", re.IGNORECASE), SEVERITY_WARNING),
    ("extracted-catalog", re.compile(r"catalog-bundle\.json$", re.IGNORECASE), SEVERITY_ERROR),
    ("environment-file", re.compile(r"^\.env(?:\..+)?$"), SEVERITY_ERROR),
)

# A JSON file with more message entries than this looks like a redistributed
# translation catalog rather than a test fixture.
MAX_JSON_ENTRIES = 500


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    severity: str
    detail: str

    def render(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"[{self.severity}] {where}: {self.rule}: {self.detail}"


def _mask(value: str) -> str:
    """Describe a match without revealing it."""
    if len(value) <= 8:
        return f"<{len(value)} chars>"
    return f"{value[:4]}…<{len(value)} chars>"


def scan_text(text: str, path: str) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for rule, pattern, severity in CONTENT_RULES:
            for match in pattern.finditer(line):
                value = match.group(0)
                if rule == "email-address" and EMAIL_ALLOW.search(value):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=number,
                        rule=rule,
                        severity=severity,
                        detail=_mask(value),
                    )
                )
    return findings


def _looks_textual(path: Path) -> bool:
    if path.suffix.lower() in _TEXT_SUFFIXES:
        return True
    try:
        with path.open("rb") as handle:
            return b"\0" not in handle.read(4096)
    except OSError:
        return False


def _display(path: Path, root: Path, root_label: str) -> str:
    try:
        relative = str(path.relative_to(root))
    except ValueError:  # pragma: no cover
        relative = str(path)
    return relative if root_label in (".", "") else f"{root_label}/{relative}"


def scan_tree(root: Path, *, root_label: str = ".") -> list[Finding]:
    """Scan every file under ``root`` and return findings.

    ``root`` itself is not excluded; the caller decides what to point it at.
    Forbidden *directories* are reported and then skipped, so the walk never
    descends into an application bundle or an unpacked archive.
    """
    root = Path(root)
    findings: list[Finding] = []

    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIR_NAMES)

        kept: list[str] = []
        for name in dirnames:
            display = _display(Path(current) / name, root, root_label)
            matched = False
            for rule, pattern, severity in FORBIDDEN_PATH_RULES:
                if pattern.search(name):
                    findings.append(
                        Finding(
                            path=display,
                            line=0,
                            rule=rule,
                            severity=severity,
                            detail="path is excluded from this repository",
                        )
                    )
                    matched = True
            if not matched:
                kept.append(name)
        dirnames[:] = kept

        for name in filenames:
            path = Path(current) / name
            display = _display(path, root, root_label)

            for rule, pattern, severity in FORBIDDEN_PATH_RULES:
                if pattern.search(name):
                    findings.append(
                        Finding(
                            path=display,
                            line=0,
                            rule=rule,
                            severity=severity,
                            detail="path is excluded from this repository",
                        )
                    )

            if not _looks_textual(path):
                continue
            try:
                if path.stat().st_size > MAX_TEXT_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            findings.extend(scan_text(text, display))

            if path.suffix.lower() == ".json":
                entries = _json_entry_count(text)
                if entries is not None and entries > MAX_JSON_ENTRIES:
                    findings.append(
                        Finding(
                            path=display,
                            line=0,
                            rule="bulk-translation-catalog",
                            severity=SEVERITY_ERROR,
                            detail=(
                                f"{entries} top-level entries; bulk translation data "
                                f"must not be committed"
                            ),
                        )
                    )
    return findings


def _json_entry_count(text: str) -> int | None:
    """Top-level entry count of a JSON object, or ``None`` if it is not one.

    The file has already been read and is capped at :data:`MAX_TEXT_BYTES`, so
    parsing it is cheap and is exact -- a regex would miss any object that is not
    pretty-printed one key per line.
    """
    stripped = text.lstrip()
    if not stripped.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return len(data) if isinstance(data, dict) else None


def summarise(findings: list[Finding]) -> tuple[int, int]:
    errors = sum(1 for f in findings if f.severity == SEVERITY_ERROR)
    warnings = sum(1 for f in findings if f.severity == SEVERITY_WARNING)
    return errors, warnings


__all__ = [
    "ALLOW_MARKER",
    "CONTENT_RULES",
    "FORBIDDEN_PATH_RULES",
    "Finding",
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "scan_text",
    "scan_tree",
    "summarise",
]
