"""Synthetic safety tests for the candidate-only build. No real app required."""

from __future__ import annotations

import tempfile
import unittest
import subprocess
import sys
from pathlib import Path

from claude_zh_patch import compat
from scripts import build_candidate_2_26454_2 as candidate
from . import support


class CandidateBuilderSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = support.build_app(
            self.root, version="2.26454.2", bundle_id="com.anthropic.claudefordesktop"
        )
        self.target = self.root / candidate.EXPECTED_TARGET_NAME

    def test_direct_script_help_invocation_works(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "build_candidate_2_26454_2.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--catalog-dir", result.stdout)

    def test_separate_unused_target_accepted(self):
        candidate.validate_target(self.source, self.target)

    def test_existing_target_refused(self):
        self.target.mkdir()
        with self.assertRaisesRegex(candidate.CandidateBuildError, "already exists"):
            candidate.validate_target(self.source, self.target)

    def test_wrong_target_name_refused(self):
        with self.assertRaisesRegex(candidate.CandidateBuildError, "named"):
            candidate.validate_target(self.source, self.root / "Claude-3P-ZH.app")

    def test_source_target_identical_refused(self):
        with self.assertRaises(candidate.CandidateBuildError):
            candidate.validate_target(self.source, self.source)

    def test_missing_parent_refused(self):
        path = self.root / "absent" / candidate.EXPECTED_TARGET_NAME
        with self.assertRaisesRegex(candidate.CandidateBuildError, "Parent directory"):
            candidate.validate_target(self.source, path)

    def test_process_local_whitelist_restored(self):
        self.assertNotIn(candidate.CANDIDATE, compat.SUPPORTED_VERSIONS)
        with candidate._temporarily_register_exact_candidate():
            entry = compat.SUPPORTED_VERSIONS[candidate.CANDIDATE]
            self.assertFalse(entry.runtime_verified)
            self.assertEqual(
                entry.file_sha256,
                compat.SUPPORTED_VERSIONS[candidate.REFERENCE].file_sha256,
            )
        self.assertNotIn(candidate.CANDIDATE, compat.SUPPORTED_VERSIONS)

    def test_process_local_whitelist_restored_on_exception(self):
        with self.assertRaisesRegex(ValueError, "synthetic failure"):
            with candidate._temporarily_register_exact_candidate():
                raise ValueError("synthetic failure")
        self.assertNotIn(candidate.CANDIDATE, compat.SUPPORTED_VERSIONS)

    def test_without_catalog_no_build(self):
        missing_catalog = self.root / "missing"
        with self.assertRaisesRegex(candidate.CandidateBuildError, "No catalog.json"):
            candidate.build_candidate(self.source, self.target, missing_catalog)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
