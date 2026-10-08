"""Fixture builders shared by the test suite.

Every fixture is synthetic. A fixture reproduces only the *structure* this tool
matches on -- file names, anchor byte sequences, their occurrence counts -- plus
messages written for these tests. No application content is embedded anywhere.
"""

from __future__ import annotations

import hashlib
import json
import plistlib
from pathlib import Path

from claude_zh_patch import compat
from claude_zh_patch.compat import (
    EN_ALLOWLIST,
    PICKER_NAME_ANCHOR,
    PICKER_OFFER_ANCHOR,
    REL_ASSETS,
    REL_I18N,
)

#: A version tag that exists only in tests, so the real allowlist is untouched.
SYNTHETIC_VERSION = "0.0.0-synthetic"

MAIN_ASSET = "shared-2-DgffKyBW.js"
PICKER_ASSET = "c49da61a8-BM3hC-jO.js"
OFFER_ASSET = "shared-25-C8tkIaeS.js"

#: English messages for the synthetic application. Deliberately small and
#: written for these tests; several carry format arguments so that placeholder
#: comparison has something to compare.
EN_BASE = {
    "greeting": "Hello, {name}!",
    "itemCount": "{count, plural, one {# item} other {# items}}",
    "signIn": "Sign in",
    "signOut": "Sign out",
    "saved": "Saved {fileName}",
    "deleted": "Deleted 1 {noun}",
    "retry": "Try again",
    "settings": "Settings",
    "search": "Search {query}",
    "empty": "Nothing here yet",
    # An argument that exists only inside one branch, so that conditional-argument
    # handling has something to exercise.
    "sharedWith": "{count, plural, one {{name} shared this} other {{names} shared this}}",
}

EN_DYNAMIC = {
    "banner": "Update available",
    "note": "{count, plural, one {# change} other {# changes}}",
}


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def build_app(
    root: Path,
    *,
    version: str = SYNTHETIC_VERSION,
    bundle_id: str = "com.example.synthetic",
    allowlist_occurrences: int = 2,
    stray_allowlist: bool = False,
    already_patched: bool = False,
    omit_asset: str | None = None,
    name: str = "Synthetic.app",
) -> Path:
    """Create a synthetic application bundle with the expected layout."""
    app = Path(root) / name
    contents = app / "Contents"
    i18n = app / REL_I18N
    assets = app / REL_ASSETS
    i18n.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)

    (contents / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleShortVersionString": version,
                "CFBundleVersion": version,
                "CFBundleIdentifier": bundle_id,
                "CFBundleExecutable": "Synthetic",
            },
            fmt=plistlib.FMT_XML,
        )
    )

    _write_json(i18n / "en-US.json", EN_BASE)
    _write_json(i18n / "dynamic" / "en-US.json", EN_DYNAMIC)
    if already_patched:
        _write_json(i18n / "zh-Hans.json", {"greeting": "您好，{name}！"})

    writer = {
        MAIN_ASSET: f"/*synthetic*/{EN_ALLOWLIST * allowlist_occurrences}/*end*/",
        PICKER_ASSET: f"/*synthetic*/{PICKER_NAME_ANCHOR},/*end*/",
        OFFER_ASSET: f"/*synthetic*/{PICKER_OFFER_ANCHOR}/*end*/",
    }
    for filename, body in writer.items():
        if filename == omit_asset:
            continue
        (assets / filename).write_text(body, encoding="utf-8")

    if stray_allowlist:
        (assets / "shared-99-Synthetic.js").write_text(
            f"/*stray*/{EN_ALLOWLIST}/*end*/", encoding="utf-8"
        )

    return app


def register_version(
    version: str, app: Path, *, runtime_verified: bool = True
) -> compat.VersionInfo:
    """Add a synthetic version to the live allowlist for the duration of a test.

    Mutates the shared dict in place so that ``patcher``, which binds the same
    object, sees the addition.
    """
    assets = Path(app) / REL_ASSETS
    digests = {}
    for filename in compat.PATCHED_FILENAMES:
        path = assets / filename
        if path.is_file():
            digests[filename] = hashlib.sha256(path.read_bytes()).hexdigest()

    info = compat.VersionInfo(
        cfbundleversion=version,
        runtime_verified=runtime_verified,
        verified_environment="synthetic fixture",
        notes="existence confined to the test suite",
        file_sha256=digests,
    )
    compat.SUPPORTED_VERSIONS[version] = info
    return info


def unregister_version(version: str) -> None:
    compat.SUPPORTED_VERSIONS.pop(version, None)
    compat.ANCHOR_ONLY_VERSIONS.pop(version, None)


#: Sentinel meaning "use the default"; ``None`` means "supply nothing".
_DEFAULT = object()


def build_catalog(
    root: Path,
    *,
    locale: str = "zh-Hans",
    base: dict[str, str] | None = None,
    dynamic: dict[str, str] | None | object = _DEFAULT,
    overrides: dict[str, str] | None = None,
    omit_files_entry: tuple[str, ...] = (),
    manifest_overrides: dict | None = None,
    write_base_file: bool = True,
    name: str = "catalog",
) -> Path:
    """Create a synthetic catalog directory."""
    directory = Path(root) / name
    directory.mkdir(parents=True, exist_ok=True)

    if base is None:
        base = {
            "greeting": "您好，{name}！",
            "itemCount": "{count, plural, other {# 项}}",
            "signIn": "登录",
            "signOut": "退出登录",
            "saved": "已保存 {fileName}",
            "deleted": "已删除 1 个{noun}",
            "retry": "重试",
            "settings": "设置",
            # Both branches kept, so the default catalog is clean.
            "sharedWith": "{count, plural, one {{name} 共享了此内容} other {{names} 共享了此内容}}",
        }
    if dynamic is _DEFAULT:
        dynamic = {"banner": "有可用更新", "note": "{count, plural, other {# 项变更}}"}

    sections: dict[str, dict[str, str]] = {"base": base}
    if dynamic:
        sections["dynamic"] = dynamic
    if overrides is not None:
        sections["overrides"] = overrides

    files: dict[str, str] = {}
    for section, messages in sections.items():
        if section in omit_files_entry:
            continue
        filename = f"{section}.json"
        if section == "base" and not write_base_file:
            files[section] = filename  # referenced but never written
            continue
        _write_json(directory / filename, messages)
        files[section] = filename

    manifest = {
        "schemaVersion": 1,
        "locale": locale,
        "displayName": "简体中文",
        "license": "CC0-1.0 (test fixture)",
        "origin": "written for the test suite",
        "files": files,
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "catalog.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return directory


# ---------------------------------------------------------------------------
# codesign stand-ins
# ---------------------------------------------------------------------------


class FakeSigning:
    """Context manager replacing the codesign-dependent surface.

    Real code signing is exercised by ``test_integration_reference.py``; unit
    tests must not depend on a signed bundle being present.
    """

    def __init__(self, entitlements: dict | None = None) -> None:
        self.entitlements = entitlements if entitlements is not None else {}
        self.calls: list[Path] = []
        self._patchers: list = []

    def __enter__(self) -> "FakeSigning":
        from unittest import mock

        self._patchers = [
            mock.patch(
                "claude_zh_patch.bundle.verify_signature", return_value=(True, "")
            ),
            mock.patch(
                "claude_zh_patch.signing.verify", return_value=(True, "ok (fake)")
            ),
            mock.patch(
                "claude_zh_patch.signing.gatekeeper_assessment",
                return_value=(False, "rejected (fake)"),
            ),
            mock.patch(
                "claude_zh_patch.signing.read_entitlements",
                side_effect=lambda item: dict(self.entitlements),
            ),
            mock.patch("claude_zh_patch.signing.collect_signables", return_value=[]),
            # ``_sign`` is the only place a real codesign process is launched, so
            # stubbing it keeps ``resign_adhoc``'s own control flow under test
            # while making no subprocess call.
            mock.patch("claude_zh_patch.signing._sign", return_value=None),
        ]
        for patcher in self._patchers:
            patcher.start()
        return self

    def __exit__(self, *exc_info) -> None:
        for patcher in self._patchers:
            patcher.stop()


def fake_signer(target: Path):
    """Drop-in for ``signing.resign_adhoc`` used by unit tests."""
    from claude_zh_patch.signing import SigningReport

    return SigningReport(
        signed_items=(".",),
        stripped_from=(),
        removed_keys=(),
        added_keys=(),
        verified=True,
        verify_detail="ok (fake signer)",
    )
