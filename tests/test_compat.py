"""Tests for the compatibility table, the version gate and the anchor set.

These tests guard the decisions written down in docs/COMPATIBILITY.md. If one of
them fails after an edit to ``compat.py``, the edit changed which builds may be
installed, and that is exactly the change that should require justification.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from claude_zh_patch import cli, compat, patcher
from claude_zh_patch.errors import UnsupportedVersionError

from . import support


class ReferenceTableTests(unittest.TestCase):
    def test_reference_build_is_installable_and_runtime_verified(self):
        info = compat.SUPPORTED_VERSIONS.get("2.26454.0")
        self.assertIsNotNone(info, "the reference build must stay installable")
        self.assertTrue(info.runtime_verified)

    def test_desktop_2264542_is_runtime_verified_and_installable(self):
        info = compat.SUPPORTED_VERSIONS.get("2.26454.2")
        self.assertIsNotNone(info)
        self.assertTrue(info.runtime_verified)
        self.assertIn("SIP disabled", info.verified_environment)
        self.assertNotIn("2.26454.2", compat.ANCHOR_ONLY_VERSIONS)

    def test_both_verified_versions_are_installable(self):
        self.assertEqual(
            sorted(compat.SUPPORTED_VERSIONS), ["2.26454.0", "2.26454.2"]
        )

    def test_verified_builds_have_identical_target_fingerprints(self):
        self.assertEqual(
            compat.SUPPORTED_VERSIONS["2.26454.2"].file_sha256,
            compat.SUPPORTED_VERSIONS["2.26454.0"].file_sha256,
        )

    def test_recorded_digests_are_well_formed(self):
        for version, info in compat.SUPPORTED_VERSIONS.items():
            with self.subTest(version=version):
                self.assertEqual(
                    sorted(info.file_sha256), sorted(compat.PATCHED_FILENAMES)
                )
                for name, digest in info.file_sha256.items():
                    self.assertRegex(digest, r"^[0-9a-f]{64}$", name)


class AnchorConsistencyTests(unittest.TestCase):
    def test_every_anchor_names_a_patched_file(self):
        for anchor in compat.ANCHORS:
            with self.subTest(anchor=anchor.name):
                self.assertIn(anchor.filename, compat.PATCHED_FILENAMES)

    def test_anchor_needles_are_non_trivial(self):
        for anchor in compat.ANCHORS:
            with self.subTest(anchor=anchor.name):
                self.assertGreater(len(anchor.needle), 8)
                self.assertGreaterEqual(anchor.occurrences, 1)
                self.assertNotEqual(anchor.needle, anchor.replacement)

    def test_allowlist_anchor_counts_sum_to_the_scan_expectation(self):
        total = sum(
            anchor.occurrences
            for anchor in compat.ANCHORS
            if anchor.needle in compat.SCAN_ALL_JS_FOR
        )
        self.assertEqual(
            total,
            compat.SCAN_EXPECTED_TOTAL,
            "the per-file anchor counts and the whole-tree scan total disagree",
        )

    def test_outgoing_allowlist_drops_placeholder_only_at_the_end(self):
        self.assertTrue(compat.EN_ALLOWLIST.endswith('"id-ID"]'))
        self.assertEqual(compat.ZH_ALLOWLIST, compat.EN_ALLOWLIST[:-1] + ',"zh-Hans"]')
        self.assertNotIn("zh-Hans", compat.EN_ALLOWLIST)
        self.assertIn("zh-Hans", compat.ZH_ALLOWLIST)

    def test_anchored_filenames_are_distinct(self):
        names = [anchor.filename for anchor in compat.ANCHORS]
        self.assertEqual(len(names), len(set(names)))


class NoBypassFlagTests(unittest.TestCase):
    """Neither the version gate nor the format-argument check may be escapable.

    A difference the user would see is refused outright. Branch collapses that
    cannot be seen are accepted automatically, which is why no acceptance flag
    exists for either case.
    """

    FORBIDDEN = (
        ["apply", "--force"],
        ["apply", "--force-version"],
        ["apply", "--skip-version-check"],
        ["apply", "--allow-unsupported"],
        ["apply", "--ignore-version"],
        ["apply", "--unsafe"],
        ["check", "--force"],
        ["check", "--skip-version-check"],
        # Removed deliberately: it would have let a visible defect through.
        ["apply", "--accept-placeholder-mismatch"],
        ["check", "--accept-placeholder-mismatch"],
        ["lint", "--accept-placeholder-mismatch"],
        ["apply", "--ignore-placeholder-mismatch"],
        ["apply", "--ignore-missing-arguments"],
        ["apply", "--skip-lint"],
        ["apply", "--no-validate"],
    )

    def test_no_bypass_flag_is_accepted(self):
        parser = cli.build_parser()
        for argv in self.FORBIDDEN:
            with self.subTest(argv=argv):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parser.parse_args(argv)

    def test_no_subcommand_mentions_placeholder_acceptance(self):
        parser = cli.build_parser()
        rendered = parser.format_help()
        for argv in (["apply", "--help"], ["check", "--help"], ["lint", "--help"]):
            with self.subTest(argv=argv):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    with self.assertRaises(SystemExit):
                        parser.parse_args(argv)
                rendered += out.getvalue()
        self.assertNotIn("accept-placeholder", rendered)


class VersionGateBehaviourTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def tearDown(self):
        support.unregister_version(support.SYNTHETIC_VERSION)

    def test_unknown_version_is_refused_with_exit_code_3(self):
        app = support.build_app(self.root, version="9.9.9-unknown")
        with self.assertRaises(UnsupportedVersionError) as caught:
            patcher.assert_supported_version(app)
        self.assertEqual(caught.exception.exit_code, 3)

    def test_refusal_names_the_supported_versions(self):
        app = support.build_app(self.root, version="9.9.9-unknown")
        with self.assertRaises(UnsupportedVersionError) as caught:
            patcher.assert_supported_version(app)
        self.assertIn("2.26454.0", caught.exception.message)

    def test_refusal_states_there_is_no_override(self):
        app = support.build_app(self.root, version="9.9.9-unknown")
        with self.assertRaises(UnsupportedVersionError) as caught:
            patcher.assert_supported_version(app)
        self.assertIn("no flag", caught.exception.message.lower())

    def test_anchor_only_version_explains_itself(self):
        version = "0.0.0-examined"
        compat.ANCHOR_ONLY_VERSIONS[version] = "inspected statically, never run"
        self.addCleanup(compat.ANCHOR_ONLY_VERSIONS.pop, version, None)

        app = support.build_app(self.root, version=version)
        with self.assertRaises(UnsupportedVersionError) as caught:
            patcher.assert_supported_version(app)
        self.assertIn("inspected statically, never run", caught.exception.message)

    def test_registered_synthetic_version_is_accepted(self):
        app = support.build_app(self.root)
        support.register_version(support.SYNTHETIC_VERSION, app)
        info = patcher.assert_supported_version(app)
        self.assertEqual(info.cfbundleversion, support.SYNTHETIC_VERSION)

    def test_missing_bundle_is_reported_clearly(self):
        with self.assertRaises(Exception) as caught:
            patcher.assert_supported_version(self.root / "Absent.app")
        self.assertIn("not found", str(caught.exception).lower())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
