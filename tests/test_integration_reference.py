"""Opt-in integration test against a real Claude Desktop installation.

Skipped unless both environment variables are set::

    CLAUDE_ZH_PATCH_REFERENCE_APP=/path/to/Claude.app
    CLAUDE_ZH_PATCH_REFERENCE_CATALOG=/path/to/catalog

The application must be an installable version (see ``docs/COMPATIBILITY.md``)
with an intact signature. The catalog is the resource you prepared yourself; this
repository ships none.

The test copies the application into a temporary directory and re-signs the copy.
It never writes to the source bundle. Expect it to copy roughly a gigabyte and to
take a couple of minutes.

    CLAUDE_ZH_PATCH_REFERENCE_APP=... CLAUDE_ZH_PATCH_REFERENCE_CATALOG=... \\
        python3 -m unittest tests.test_integration_reference -v

A catalog whose only differences are removed plural/select branches installs
without a flag, because that is a language choosing not to inflect. A catalog
with a difference the user would actually see is refused, and this test will
report it rather than work around it.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from claude_zh_patch import bundle, catalog as catalog_mod, lifecycle, patcher, signing
from claude_zh_patch.compat import LOCALE, REL_MARKER, SUPPORTED_VERSIONS

SOURCE = os.environ.get("CLAUDE_ZH_PATCH_REFERENCE_APP")
CATALOG = os.environ.get("CLAUDE_ZH_PATCH_REFERENCE_CATALOG")

requires_reference = unittest.skipUnless(
    SOURCE and CATALOG,
    "set CLAUDE_ZH_PATCH_REFERENCE_APP and CLAUDE_ZH_PATCH_REFERENCE_CATALOG",
)


@requires_reference
class ReferenceBuildIntegrationTests(unittest.TestCase):
    """End-to-end run against a genuine signed bundle."""

    @classmethod
    def setUpClass(cls):
        cls.source = Path(SOURCE).expanduser()
        version = bundle.read_version(cls.source)
        if version not in SUPPORTED_VERSIONS:
            raise unittest.SkipTest(
                f"{version} is not an installable version; refusing to run"
            )
        ok, detail = bundle.verify_signature(cls.source)
        if not ok:
            raise unittest.SkipTest(f"source signature does not verify: {detail[:400]}")

        cls._tmp = tempfile.TemporaryDirectory()
        cls.target = Path(cls._tmp.name) / "Integration.app"
        cls.catalog = catalog_mod.load_catalog(Path(CATALOG).expanduser())

        try:
            cls.result = patcher.apply(cls.source, cls.target, cls.catalog)
        except Exception as exc:  # noqa: BLE001
            cls._tmp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_signature_verifies_after_patching(self):
        ok, detail = signing.verify(self.target)
        self.assertTrue(ok, detail[-800:])

    def test_no_restricted_entitlement_survives(self):
        entitlements = signing.read_entitlements(self.target) or {}
        restricted = sorted(key for key in entitlements if signing.is_restricted(key))
        self.assertEqual(restricted, [])
        self.assertIn("com.apple.security.cs.disable-library-validation", entitlements)

    def test_allowlist_is_rewritten(self):
        from claude_zh_patch import compat

        assets = bundle.asset_dir(self.target)
        for anchor in compat.ANCHORS:
            text = (assets / anchor.filename).read_text(encoding="utf-8")
            with self.subTest(anchor=anchor.name):
                self.assertEqual(text.count(anchor.needle), 0)
                self.assertGreaterEqual(text.count(anchor.replacement), 1)

    def test_target_language_files_are_installed(self):
        i18n = bundle.i18n_dir(self.target)
        for relative in (f"{LOCALE}.json", f"dynamic/{LOCALE}.json"):
            with self.subTest(file=relative):
                self.assertTrue((i18n / relative).is_file())

    def test_marker_is_present_and_free_of_local_paths(self):
        rendered = (self.target / REL_MARKER).read_text(encoding="utf-8")
        marker = json.loads(rendered)
        self.assertEqual(marker["patch"], patcher.MARKER_PATCH_ID)
        self.assertNotIn(str(Path.home()), rendered)

    def test_verify_command_accepts_the_result(self):
        report = lifecycle.verify(self.target)
        self.assertTrue(report.ok)
        self.assertEqual(report.restricted_entitlements, ())

    def test_the_source_bundle_was_not_modified(self):
        ok, _ = bundle.verify_signature(self.source)
        self.assertTrue(ok, "the source bundle's signature changed")
        self.assertFalse((self.source / REL_MARKER).exists())
        self.assertFalse((bundle.i18n_dir(self.source) / f"{LOCALE}.json").exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
