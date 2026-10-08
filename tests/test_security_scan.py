"""Tests for the secret / third-party-material scanner.

Synthetic secrets are assembled at run time rather than written literally, so
that scanning this repository never reports its own test fixtures.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from claude_zh_patch import security_scan


def rules_for(text: str) -> set[str]:
    return {finding.rule for finding in security_scan.scan_text(text, "sample.txt")}


class CredentialRuleTests(unittest.TestCase):
    def test_anthropic_api_key(self):
        secret = "sk-ant-" + "A" * 28
        self.assertIn("anthropic-api-key", rules_for(f"value={secret}"))

    def test_github_token(self):
        self.assertIn("github-token", rules_for("token=" + "ghp_" + "b" * 36))

    def test_github_fine_grained_token(self):
        self.assertIn("github-token", rules_for("x=" + "github_pat_" + "c" * 30))

    def test_aws_access_key_id(self):
        self.assertIn("aws-access-key-id", rules_for("id=" + "AKIA" + "D" * 16))

    def test_private_key_block(self):
        line = "-----BEGIN " + "RSA PRIVATE KEY" + "-----"
        self.assertIn("private-key-block", rules_for(line))

    def test_bearer_token(self):
        self.assertIn("bearer-token", rules_for("Authorization: Bearer " + "e" * 40))

    def test_assigned_secret(self):
        line = 'api_key = "' + "f" * 24 + '"'
        self.assertIn("assigned-secret", rules_for(line))

    def test_slack_token(self):
        self.assertIn("slack-token", rules_for("x=" + "xoxb-" + "1" * 12))

    def test_home_directory_path(self):
        self.assertIn("home-directory-path", rules_for("at /Users/" + "somebody" + "/x"))

    def test_chat_transcript_shape(self):
        line = '"role"' + ": " + '"user",'
        self.assertIn("chat-transcript", rules_for(line))

    def test_plain_text_is_clean(self):
        self.assertEqual(rules_for("Sign in\nSettings\n{count, plural, other {#}}"), set())


class EmailRuleTests(unittest.TestCase):
    def test_flags_a_real_looking_address(self):
        address = "a" + "@" + "realcorp.com"
        self.assertIn("email-address", rules_for("mail " + address))

    def test_allows_documentation_addresses(self):
        for local in ("noreply", "someone"):
            with self.subTest(local=local):
                self.assertNotIn(
                    "email-address", rules_for(f"{local}@example.com")
                )

    def test_rule_has_warning_severity(self):
        address = "a" + "@" + "realcorp.com"
        findings = [f for f in security_scan.scan_text(address, "x") if f.rule == "email-address"]
        self.assertTrue(findings)
        self.assertEqual(findings[0].severity, security_scan.SEVERITY_WARNING)


class MaskingTests(unittest.TestCase):
    def test_the_matched_value_is_not_echoed(self):
        secret = "sk-ant-" + "Z" * 30
        findings = security_scan.scan_text(f"key={secret}", "sample.txt")
        self.assertTrue(findings)
        for finding in findings:
            self.assertNotIn(secret, finding.detail)
            self.assertNotIn(secret[6:], finding.detail)

    def test_mask_describes_the_length(self):
        secret = "sk-ant-" + "Z" * 30
        findings = security_scan.scan_text(f"key={secret}", "sample.txt")
        self.assertIn(str(len(secret)), findings[0].detail)


class AllowMarkerTests(unittest.TestCase):
    def test_marker_suppresses_the_line(self):
        secret = "sk-ant-" + "Q" * 28
        line = f"example = {secret}  # {security_scan.ALLOW_MARKER}"
        self.assertEqual(rules_for(line), set())

    def test_marker_only_affects_its_own_line(self):
        secret = "sk-ant-" + "Q" * 28
        text = f"ok = {secret}  # {security_scan.ALLOW_MARKER}\nbad = {secret}\n"
        self.assertIn("anthropic-api-key", rules_for(text))


class PathRuleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _rules_for(self, name: str, *, directory: bool = False) -> set[str]:
        path = self.root / name
        if directory:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.write_text("harmless\n", encoding="utf-8")
        return {finding.rule for finding in security_scan.scan_tree(self.root)}

    def test_app_bundle(self):
        self.assertIn("app-bundle", self._rules_for("Claude.app", directory=True))

    def test_electron_archive(self):
        self.assertIn("electron-archive", self._rules_for("app.asar"))

    def test_environment_file(self):
        self.assertIn("environment-file", self._rules_for(".env"))

    def test_provisioning_profile(self):
        self.assertIn("provisioning-profile", self._rules_for("embedded.provisionprofile"))

    def test_key_material(self):
        self.assertIn("key-material", self._rules_for("signing.p12"))

    def test_binary_library_is_a_warning(self):
        path = self.root / "libthing.dylib"
        path.write_text("harmless\n", encoding="utf-8")
        found = [f for f in security_scan.scan_tree(self.root) if f.rule == "binary-library"]
        self.assertTrue(found)
        self.assertEqual(found[0].severity, security_scan.SEVERITY_WARNING)

    def test_extracted_catalog_bundle(self):
        self.assertIn(
            "extracted-catalog", self._rules_for("claude-zh-Hans-catalog-bundle.json")
        )

    def test_ordinary_files_are_clean(self):
        self._rules_for("README.md")
        self.assertEqual(security_scan.scan_tree(self.root), [])


class BulkCatalogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_a_large_json_object_is_rejected(self):
        import json

        payload = {f"key{index}": "value" for index in range(600)}
        (self.root / "big.json").write_text(json.dumps(payload), encoding="utf-8")
        rules = {f.rule for f in security_scan.scan_tree(self.root)}
        self.assertIn("bulk-translation-catalog", rules)

    def test_a_small_json_object_is_fine(self):
        import json

        (self.root / "small.json").write_text(
            json.dumps({"a": "1", "b": "2"}), encoding="utf-8"
        )
        self.assertEqual(security_scan.scan_tree(self.root), [])

    def test_an_array_is_not_treated_as_a_catalog(self):
        import json

        (self.root / "list.json").write_text(
            json.dumps([f"item{index}" for index in range(600)]), encoding="utf-8"
        )
        self.assertEqual(security_scan.scan_tree(self.root), [])


class ScanTreeMechanicsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_git_directory_is_skipped(self):
        git = self.root / ".git"
        git.mkdir()
        (git / "config").write_text(
            "key = " + "sk-ant-" + "M" * 28, encoding="utf-8"
        )
        self.assertEqual(security_scan.scan_tree(self.root), [])

    def test_binary_files_are_skipped_for_content_rules(self):
        (self.root / "blob.bin").write_bytes(b"\x00\x01" + b"sk-ant-" + b"N" * 28)
        self.assertEqual(security_scan.scan_tree(self.root), [])

    def test_findings_carry_a_relative_path(self):
        (self.root / "nested").mkdir()
        (self.root / "nested" / "x.txt").write_text(
            "v=" + "sk-ant-" + "P" * 28, encoding="utf-8"
        )
        findings = security_scan.scan_tree(self.root)
        self.assertTrue(findings)
        self.assertEqual(findings[0].path, "nested/x.txt")
        self.assertGreater(findings[0].line, 0)

    def test_summarise_counts_by_severity(self):
        address = "a" + "@" + "realcorp.com"
        findings = security_scan.scan_text(
            "v=" + "sk-ant-" + "P" * 28 + "\nmail " + address, "x"
        )
        errors, warnings = security_scan.summarise(findings)
        self.assertGreaterEqual(errors, 1)
        self.assertGreaterEqual(warnings, 1)


class RepositoryIsCleanTests(unittest.TestCase):
    """The repository itself must pass its own scan."""

    def test_no_findings_in_this_repository(self):
        repository = Path(__file__).resolve().parent.parent
        findings = security_scan.scan_tree(repository, root_label=repository.name)
        rendered = "\n".join(finding.render() for finding in findings)
        self.assertEqual(findings, [], f"the repository is not clean:\n{rendered}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
