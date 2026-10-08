"""Tests that the documentation the project promises actually exists.

These are cheap guards against a release being cut with a missing disclaimer or
with the version gate described inaccurately.
"""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent

#: sha256 of the canonical Apache License 2.0 text as published by the ASF.
CANONICAL_APACHE_2_0 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"

REQUIRED_FILES = (
    "LICENSE",
    "NOTICE",
    "README.md",
    "README.zh-Hans.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "docs/INSTALL.md",
    "docs/INSTALL.zh-Hans.md",
    "docs/COMPATIBILITY.md",
    "docs/TROUBLESHOOTING.md",
    "docs/TROUBLESHOOTING.zh-Hans.md",
    "docs/CATALOG-FORMAT.md",
    "docs/DISCLAIMER.md",
    "docs/SECURITY.md",
    "schema/catalog.schema.json",
    "schema/messages.schema.json",
    "templates/catalog/catalog.json",
    "templates/catalog/base.json",
)


def read(relative: str) -> str:
    return (REPOSITORY / relative).read_text(encoding="utf-8")


def squash(text: str) -> str:
    """Collapse whitespace so an assertion is not broken by prose wrapping."""
    return " ".join(text.split())


class RequiredFileTests(unittest.TestCase):
    def test_every_required_file_exists_and_is_not_empty(self):
        for relative in REQUIRED_FILES:
            with self.subTest(file=relative):
                path = REPOSITORY / relative
                self.assertTrue(path.is_file(), f"missing: {relative}")
                self.assertGreater(len(path.read_text(encoding="utf-8").strip()), 0)


class LicenceTests(unittest.TestCase):
    def test_licence_text_is_the_canonical_apache_2_0(self):
        digest = hashlib.sha256((REPOSITORY / "LICENSE").read_bytes()).hexdigest()
        self.assertEqual(digest, CANONICAL_APACHE_2_0)

    def test_notice_scopes_the_licence_to_original_work_only(self):
        text = read("NOTICE")
        for phrase in ("Anthropic", "not covered", "translation"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


class DisclosureTests(unittest.TestCase):
    """The claims the READMEs make must cover every required disclosure.

    These exist so that a disclosure cannot be quietly dropped before a release.
    """

    def setUp(self):
        self.readme = squash(read("README.md"))
        self.readme_zh = squash(read("README.zh-Hans.md"))
        self.disclaimer = squash(read("docs/DISCLAIMER.md"))

    def assert_mentions(self, haystack: str, *phrases: str):
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, haystack)

    def test_not_an_official_project(self):
        self.assert_mentions(
            self.readme.lower(),
            "unofficial",
            "not affiliated",
            "anthropic",
        )

    def test_shipping_no_translation_resource(self):
        """Both READMEs must say the user has to supply their own catalog."""
        self.assert_mentions(
            self.readme.lower(),
            "no chinese translation resource in this repository",
            "--catalog-dir",
            "responsible for having the right to use it",
        )
        self.assert_mentions(
            self.readme_zh,
            "没有任何中文翻译资源",
            "--catalog-dir",
            "自行负责拥有使用它的权利",
        )

    def test_sip_enabled_compatibility_is_declared_unconfirmed(self):
        """The verification machine had SIP off; both READMEs must say so."""
        self.assert_mentions(
            self.readme.lower(),
            "compatibility with sip enabled is unconfirmed",
            "system integrity protection",
            "has been tested",
        )
        self.assert_mentions(
            self.readme_zh,
            "SIP 开启环境下的兼容性尚未确认",
            "系统完整性保护",
        )

    def test_does_not_ask_the_user_to_weaken_the_system(self):
        combined = (self.readme + self.readme_zh + self.disclaimer).lower()
        self.assertIn("should not disable it", combined)
        self.assert_mentions(self.disclaimer.lower(), "do not disable")

    def test_discloses_the_verification_environment(self):
        combined = squash(
            read("README.md") + read("docs/DISCLAIMER.md") + read("docs/COMPATIBILITY.md")
        ).lower()
        self.assert_mentions(combined, "sip", "gatekeeper", "ad-hoc")

    def test_does_not_promise_universal_compatibility(self):
        combined = (self.readme + self.disclaimer).lower()
        self.assert_mentions(combined, "not a guarantee", "only")
        for forbidden in ("works on all mac", "all macos versions are supported"):
            self.assertNotIn(forbidden, combined)

    def test_states_what_may_break(self):
        self.assert_mentions(self.disclaimer.lower(), "keychain", "native")


class VersionConsistencyTests(unittest.TestCase):
    """There is one version identifier, and the tag names it.

    ``pyproject.toml`` reads ``__version__`` rather than restating it, so nothing
    can drift apart silently.
    """

    def setUp(self):
        self.pyproject = read("pyproject.toml")
        self.init = read("src/claude_zh_patch/__init__.py")
        self.changelog = read("CHANGELOG.md")

    def test_the_version_attribute_is_the_release_name(self):
        from claude_zh_patch import __version__

        self.assertEqual(__version__, "0.1.0-beta")

    def test_tool_version_follows_the_same_attribute(self):
        from claude_zh_patch import __version__, compat

        self.assertEqual(compat.TOOL_VERSION, __version__)

    def _tables(self) -> dict[str, str]:
        """Split pyproject.toml into its ``[table]`` blocks."""
        blocks: dict[str, str] = {}
        current = ""
        for line in self.pyproject.splitlines():
            if line.startswith("[") and line.endswith("]"):
                current = line.strip("[]")
                blocks[current] = ""
            elif current:
                blocks[current] += line + "\n"
        return blocks

    def test_pyproject_does_not_restate_the_version(self):
        self.assertIn('dynamic = ["version"]', self.pyproject)
        project = self._tables().get("project", "")
        self.assertTrue(project, "no [project] table found")
        self.assertNotRegex(
            project,
            r"(?m)^\s*version\s*=",
            "the [project] table must derive the version, not state it",
        )

    def test_pyproject_reads_the_attribute(self):
        dynamic = self._tables().get("tool.setuptools.dynamic", "")
        self.assertIn('version = { attr = "claude_zh_patch.__version__" }', dynamic)

    def test_the_version_attribute_is_a_plain_literal(self):
        """setuptools reads it by static analysis, so it must stay a literal."""
        self.assertRegex(self.init, r'(?m)^__version__ = "0\\.1\\.0-beta"$')

    def test_changelog_has_a_section_for_this_version(self):
        self.assertIn("## [0.1.0-beta]", self.changelog)

    def test_changelog_explains_the_normalised_form(self):
        self.assertIn("0.1.0b0", self.changelog)

    def test_the_version_looks_like_a_prerelease(self):
        """A pre-release must not be mistakable for a stable version."""
        from claude_zh_patch import __version__

        self.assertRegex(__version__, r"^\d+\.\d+\.\d+-(alpha|beta|rc)\d*$")


class CompatibilityMatrixTests(unittest.TestCase):
    def setUp(self):
        self.matrix = squash(read("docs/COMPATIBILITY.md"))

    def test_lists_the_verified_build(self):
        self.assertIn("2.26454.0", self.matrix)

    def test_records_runtime_verified_build_and_limits(self):
        self.assertIn("2.26454.2", self.matrix)
        self.assertIn("Runtime-verified", self.matrix)
        self.assertIn("SIP disabled", self.matrix)
        self.assertIn("Gatekeeper", self.matrix)
        self.assertIn("Keychain", self.matrix)
        self.assertNotIn("2.26454.2` | **Not installable**", self.matrix)

    def test_records_the_identical_digest_finding(self):
        self.assertIn(
            "d5e17aa1e80c60af3784988242e1c673308c5746bfdb45a1c8b449da17f6effb",
            self.matrix,
            "the matrix should record that both builds share the patched files",
        )

    def test_describes_how_a_version_is_added(self):
        self.assertIn("native", self.matrix.lower())



if __name__ == "__main__":  # pragma: no cover
    unittest.main()
