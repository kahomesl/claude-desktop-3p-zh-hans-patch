"""Unit tests for the read-only 2.26454.2 preflight.

All bundles are synthetic; no Anthropic code or catalogs are checked in.
The candidate's real-byte fingerprints must be verified on the user's Mac.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from claude_zh_patch import compat
from scripts import inspect_2_26454_2 as probe
from . import support


class CandidatePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = support.build_app(
            self.root,
            version="2.26454.2",
            bundle_id=probe.EXPECTED_BUNDLE_ID,
        )

    def _valid_mocks(self):
        recorded = compat.SUPPORTED_VERSIONS["2.26454.0"].file_sha256
        return (
            mock.patch.object(probe.bundle, "verify_signature", return_value=(True, "")),
            mock.patch.object(
                probe.bundle,
                "file_sha256",
                side_effect=lambda path: recorded[Path(path).name],
            ),
            mock.patch.object(probe.shutil, "which", return_value="/usr/bin/node"),
            mock.patch.object(
                probe.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                ),
            ),
        )

    def _inspect_valid(self):
        with self._valid_mocks()[0] as _:
            pass

    def _inspect_with_mocks(self):
        patches = self._valid_mocks()
        with patches[0], patches[1], patches[2], patches[3]:
            return probe.inspect_app(self.app)

    def test_valid_structure_is_only_a_static_pass(self):
        report = self._inspect_with_mocks()
        self.assertEqual(report["status"], "STATIC_PASS_RUNTIME_UNVERIFIED")
        self.assertFalse(report["runtimeVerified"])
        self.assertFalse(report["installable"])
        self.assertEqual(report["matchedAnchors"], 3)
        self.assertEqual(report["javascriptSyntax"], "PASS")

    def test_probe_never_modifies_source(self):
        before = {
            p.relative_to(self.app): p.read_bytes()
            for p in self.app.rglob("*")
            if p.is_file()
        }
        self._inspect_with_mocks()
        after = {
            p.relative_to(self.app): p.read_bytes()
            for p in self.app.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)

    def test_other_version_is_refused_before_signing(self):
        other = support.build_app(
            self.root,
            version="2.26454.0",
            bundle_id=probe.EXPECTED_BUNDLE_ID,
            name="Other.app",
        )
        with self.assertRaises(probe.PreflightError) as caught:
            probe.inspect_app(other)
        self.assertEqual(caught.exception.code, 3)

    def test_unexpected_bundle_identifier_is_refused(self):
        other = support.build_app(
            self.root, version="2.26454.2", name="Other.app"
        )
        with self.assertRaisesRegex(probe.PreflightError, "bundle identifier"):
            probe.inspect_app(other)

    def test_invalid_signature_is_refused(self):
        with mock.patch.object(
            probe.bundle, "verify_signature", return_value=(False, "invalid signature")
        ):
            with self.assertRaisesRegex(probe.PreflightError, "signature is invalid"):
                probe.inspect_app(self.app)

    def test_existing_chinese_catalog_is_refused(self):
        other = support.build_app(
            self.root, version="2.26454.2", bundle_id=probe.EXPECTED_BUNDLE_ID,
            already_patched=True, name="Patched.app"
        )
        with mock.patch.object(
            probe.bundle, "verify_signature", return_value=(True, "")
        ):
            with self.assertRaisesRegex(probe.PreflightError, "already contains"):
                probe.inspect_app(other)

    def test_changed_anchor_is_refused(self):
        anchor = compat.ANCHORS[0]
        path = self.app / compat.REL_ASSETS / anchor.filename
        path.write_text("no locale allowlist here", encoding="utf-8")
        with mock.patch.object(
            probe.bundle, "verify_signature", return_value=(True, "")
        ):
            with self.assertRaisesRegex(probe.PreflightError, "Anchor"):
                probe.inspect_app(self.app)

    def test_changed_digest_is_refused(self):
        with mock.patch.object(
            probe.bundle, "verify_signature", return_value=(True, "")
        ), mock.patch.object(probe.bundle, "file_sha256", return_value="f" * 64):
            with self.assertRaisesRegex(probe.PreflightError, "SHA-256 mismatch"):
                probe.inspect_app(self.app)

    def test_stray_allowlist_is_refused(self):
        extra = self.app / compat.REL_ASSETS / "extra.js"
        extra.write_text(compat.EN_ALLOWLIST, encoding="utf-8")
        with mock.patch.object(
            probe.bundle, "verify_signature", return_value=(True, "")
        ), mock.patch.object(
            probe.bundle, "file_sha256",
            side_effect=lambda path:
                compat.SUPPORTED_VERSIONS["2.26454.0"].file_sha256[Path(path).name]
        ):
            with self.assertRaisesRegex(probe.PreflightError, "Unknown allowlist"):
                probe.inspect_app(self.app)

    def test_missing_node_is_blocking(self):
        patches = self._valid_mocks()
        with patches[0], patches[1], mock.patch.object(probe.shutil, "which", return_value=None):
            with self.assertRaisesRegex(probe.PreflightError, "Node.js is required"):
                probe.inspect_app(self.app)

    def test_javascript_syntax_failure_is_blocking(self):
        patches = self._valid_mocks()
        with patches[0], patches[1], patches[2], mock.patch.object(
            probe.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="Unexpected token"
            ),
        ):
            with self.assertRaisesRegex(probe.PreflightError, "syntax validation"):
                probe.inspect_app(self.app)

    def test_cli_returns_three_for_wrong_version(self):
        other = support.build_app(
            self.root,
            version="9.9.9",
            bundle_id=probe.EXPECTED_BUNDLE_ID,
            name="Unknown.app",
        )
        with redirect_stderr(io.StringIO()):
            self.assertEqual(probe.main(["--app", str(other)]), 3)


if __name__ == "__main__":
    unittest.main()
