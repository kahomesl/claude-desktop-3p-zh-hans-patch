"""Tests for the command line surface: exit codes and refusal behaviour."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from claude_zh_patch import cli, lifecycle
from claude_zh_patch.errors import (
    EXIT_CATALOG,
    EXIT_OK,
    EXIT_UNSUPPORTED_VERSION,
)

from . import support


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class NoArgumentsTests(unittest.TestCase):
    def test_prints_help_and_returns_usage(self):
        code, out, _ = run()
        self.assertEqual(code, 2)
        self.assertIn("apply", out)


class VersionCommandTests(unittest.TestCase):
    def test_lists_both_versions(self):
        code, out, _ = run("version")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("2.26454.0", out)
        self.assertIn("2.26454.2", out)

    def test_marks_the_reference_build_as_runtime_verified(self):
        _, out, _ = run("version")
        self.assertIn("runtime-verified", out)

    def test_json_output(self):
        code, out, _ = run("--json", "version")
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(payload["installable"], ["2.26454.0", "2.26454.2"])
        self.assertEqual(payload["examinedNotInstallable"], [])


class UnsupportedVersionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.app = support.build_app(self.root, version="9.9.9-unknown", name="Odd.app")

    def test_check_returns_exit_code_3(self):
        code, _, err = run("check", "--app", str(self.app))
        self.assertEqual(code, EXIT_UNSUPPORTED_VERSION)
        self.assertIn("not a supported version", err)

    def test_apply_returns_exit_code_3_before_needing_a_catalog(self):
        catalog = support.build_catalog(self.root)
        code, _, err = run(
            "apply",
            "--app",
            str(self.app),
            "--target",
            str(self.root / "Out.app"),
            "--catalog-dir",
            str(catalog),
        )
        self.assertEqual(code, EXIT_UNSUPPORTED_VERSION)
        self.assertFalse((self.root / "Out.app").exists())


class MissingCatalogTests(unittest.TestCase):
    def test_apply_without_a_catalog_dir_explains_itself(self):
        code, _, err = run("apply")
        self.assertEqual(code, EXIT_CATALOG)
        self.assertIn("--catalog-dir", err)
        self.assertIn("ships no translation data", err)

    def test_apply_with_a_missing_catalog_directory(self):
        code, _, err = run("apply", "--catalog-dir", "/nonexistent/catalog")
        self.assertEqual(code, EXIT_CATALOG)
        self.assertIn("not found", err)


class PipelineCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.addCleanup(support.unregister_version, support.SYNTHETIC_VERSION)
        self.app = support.build_app(self.root, name="Source.app")
        support.register_version(support.SYNTHETIC_VERSION, self.app)
        self.catalog = support.build_catalog(self.root)
        self.target = self.root / "Installed.app"

    def test_check_succeeds_and_writes_nothing(self):
        before = sorted(p.name for p in self.root.rglob("*"))
        code, out, _ = run("check", "--app", str(self.app), "--catalog-dir", str(self.catalog))
        after = sorted(p.name for p in self.root.rglob("*"))
        self.assertEqual(code, EXIT_OK)
        self.assertIn("passed", out)
        self.assertEqual(before, after)

    def test_apply_then_verify_then_rollback(self):
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code, out, _ = run(
                "apply",
                "--app",
                str(self.app),
                "--target",
                str(self.target),
                "--catalog-dir",
                str(self.catalog),
            )
            self.assertEqual(code, EXIT_OK, out)
            self.assertIn("ad-hoc", out)
            self.assertIn("Gatekeeper", out)
            self.assertIn("Keychain", out)
            self.assertTrue(self.target.is_dir())

            code, out, _ = run("verify", "--target", str(self.target))
            self.assertEqual(code, EXIT_OK, out)
            self.assertIn("static check only", out)

        # The CLI's rollback targets the real Trash, so it is stubbed here; the
        # real move is exercised in test_lifecycle with an injected directory.
        trash = self.root / "Trash"
        with mock.patch.object(
            lifecycle, "rollback", return_value=trash / "moved"
        ) as rollback:
            code, out, _ = run("rollback", "--target", str(self.target))
        self.assertEqual(code, EXIT_OK, out)
        self.assertIn("Trash", out)
        rollback.assert_called_once_with(Path(str(self.target)))

    def test_apply_json_output_is_parseable(self):
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code, out, _ = run(
                "--json",
                "apply",
                "--app",
                str(self.app),
                "--target",
                str(self.target),
                "--catalog-dir",
                str(self.catalog),
            )
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertTrue(payload["signatureVerified"])
        self.assertEqual(payload["sourceVersion"], support.SYNTHETIC_VERSION)

    def test_apply_twice_is_refused(self):
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            run(
                "apply",
                "--app",
                str(self.app),
                "--target",
                str(self.target),
                "--catalog-dir",
                str(self.catalog),
            )
            code, _, err = run(
                "apply",
                "--app",
                str(self.app),
                "--target",
                str(self.target),
                "--catalog-dir",
                str(self.catalog),
            )
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

    def test_verify_of_an_unmanaged_bundle_fails(self):
        plain = support.build_app(self.root, name="Unmanaged.app")
        code, _, err = run("verify", "--target", str(plain))
        self.assertEqual(code, 1)
        self.assertIn("marker", err)

    def test_rollback_only_accepts_a_marked_copy(self):
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            run(
                "apply",
                "--app",
                str(self.app),
                "--target",
                str(self.target),
                "--catalog-dir",
                str(self.catalog),
            )
        destination = lifecycle.rollback(self.target, trash=self.root / "Trash")
        self.assertTrue(destination.is_dir())


class KeysCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.addCleanup(support.unregister_version, support.SYNTHETIC_VERSION)
        self.app = support.build_app(self.root, name="Source.app")
        support.register_version(support.SYNTHETIC_VERSION, self.app)

    def test_emits_keys_with_empty_values(self):
        out_path = self.root / "base.json"
        code, out, err = run("keys", "--app", str(self.app), "--out", str(out_path))
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(payload), sorted(support.EN_BASE))
        self.assertTrue(all(value == "" for value in payload.values()))
        self.assertIn("no text", err)

    def test_does_not_export_english_text(self):
        out_path = self.root / "base.json"
        run("keys", "--app", str(self.app), "--out", str(out_path))
        rendered = out_path.read_text(encoding="utf-8")
        for english in support.EN_BASE.values():
            with self.subTest(english=english):
                self.assertNotIn(english, rendered)

    def test_refuses_to_overwrite_without_force(self):
        out_path = self.root / "base.json"
        out_path.write_text("{}", encoding="utf-8")
        code, _, err = run("keys", "--app", str(self.app), "--out", str(out_path))
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

    def test_force_overwrites(self):
        out_path = self.root / "base.json"
        out_path.write_text("{}", encoding="utf-8")
        code, _, _ = run("keys", "--app", str(self.app), "--out", str(out_path), "--force")
        self.assertEqual(code, EXIT_OK)


class LintCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.addCleanup(support.unregister_version, support.SYNTHETIC_VERSION)
        self.app = support.build_app(self.root, name="Source.app")
        support.register_version(support.SYNTHETIC_VERSION, self.app)

    def _bad_catalog(self) -> Path:
        base = {
            "greeting": "您好！",  # {name} dropped
            "itemCount": "{count, plural, other {# 项}}",
            "signIn": "登录",
            "signOut": "退出登录",
            "saved": "已保存 {fileName}",
            "deleted": "已删除 1 个{noun}",
            "retry": "重试",
            "settings": "设置",
            "sharedWith": "{count, plural, one {{name} 共享了此内容} other {{names} 共享了此内容}}",
        }
        return support.build_catalog(self.root, base=base, name="bad")

    def _branch_collapsing_catalog(self) -> Path:
        """A catalog that keeps only the plural branch, which some languages do."""
        base = {
            "greeting": "您好，{name}！",
            "itemCount": "{count, plural, other {# 项}}",
            "signIn": "登录",
            "signOut": "退出登录",
            "saved": "已保存 {fileName}",
            "deleted": "已删除 1 个{noun}",
            "retry": "重试",
            "settings": "设置",
            "sharedWith": "{count, plural, other {{names} 共享了此内容}}",
        }
        return support.build_catalog(self.root, base=base, name="collapsed")

    def test_lint_requires_a_catalog(self):
        code, _, err = run("lint", "--app", str(self.app))
        self.assertEqual(code, EXIT_CATALOG)
        self.assertIn("--catalog-dir", err)

    def test_lint_passes_a_good_catalog(self):
        good = support.build_catalog(self.root, name="good")
        code, out, _ = run("lint", "--app", str(self.app), "--catalog-dir", str(good))
        self.assertEqual(code, EXIT_OK, out)
        self.assertIn("Installable", out)
        self.assertIn("Format-argument defects", out)

    def test_lint_blocks_a_bad_catalog_and_explains_why(self):
        code, out, _ = run("lint", "--app", str(self.app), "--catalog-dir", str(self._bad_catalog()))
        self.assertEqual(code, EXIT_CATALOG)
        self.assertIn("Not installable", out)
        self.assertIn("base[greeting]", out)
        self.assertIn("drops a format argument", out)
        self.assertIn("Application arguments: {name}", out)
        self.assertIn("Supplied arguments: (none)", out)
        self.assertIn("Not rendered: {name}", out)

    def test_lint_report_does_not_repeat_the_placeholder_findings(self):
        code, out, _ = run("lint", "--app", str(self.app), "--catalog-dir", str(self._bad_catalog()))
        self.assertEqual(code, EXIT_CATALOG)
        self.assertEqual(out.count("base[greeting]"), 1, out)
        self.assertIn("## Other findings\n\nNone.", out)

    def test_lint_mentions_no_acceptance_flag(self):
        _, out, _ = run("lint", "--app", str(self.app), "--catalog-dir", str(self._bad_catalog()))
        self.assertNotIn("accept-placeholder", out)

    def test_lint_report_file_is_written(self):
        bad = self._bad_catalog()
        out_path = self.root / "report.md"
        code, _, err = run(
            "lint",
            "--app",
            str(self.app),
            "--catalog-dir",
            str(bad),
            "--report",
            str(out_path),
        )
        self.assertEqual(code, EXIT_CATALOG)
        self.assertIn("report written", err)
        text = out_path.read_text(encoding="utf-8")
        self.assertIn("# Language resource report", text)
        self.assertIn("base[greeting]", text)

    def test_lint_report_contains_no_english_source_text(self):
        bad = self._bad_catalog()
        out_path = self.root / "report.md"
        run("lint", "--app", str(self.app), "--catalog-dir", str(bad), "--report", str(out_path))
        text = out_path.read_text(encoding="utf-8")
        for english in support.EN_BASE.values():
            with self.subTest(english=english):
                self.assertNotIn(english, text)

    def test_lint_json_lists_each_defect(self):
        bad = self._bad_catalog()
        code, out, _ = run("--json", "lint", "--app", str(self.app), "--catalog-dir", str(bad))
        self.assertEqual(code, EXIT_CATALOG)
        payload = json.loads(out)
        self.assertFalse(payload["installable"])
        self.assertEqual(len(payload["defects"]), 1)
        entry = payload["defects"][0]
        self.assertEqual(entry["key"], "greeting")
        self.assertTrue(entry["isDefect"])
        self.assertEqual(entry["applicationArguments"], ["name"])
        self.assertEqual(entry["suppliedArguments"], [])
        self.assertEqual(entry["requiredMissing"], ["name"])

    def test_lint_writes_nothing_into_the_source_bundle(self):
        good = support.build_catalog(self.root, name="good")
        before = sorted(p.name for p in self.app.rglob("*"))
        run("lint", "--app", str(self.app), "--catalog-dir", str(good))
        after = sorted(p.name for p in self.app.rglob("*"))
        self.assertEqual(before, after)

    def test_lint_accepts_a_branch_collapse_without_a_flag(self):
        code, out, _ = run(
            "lint",
            "--app",
            str(self.app),
            "--catalog-dir",
            str(self._branch_collapsing_catalog()),
        )
        self.assertEqual(code, EXIT_OK, out)
        self.assertIn("Installable", out)
        self.assertIn("Branch collapses accepted (1)", out)
        self.assertIn("base[sharedWith]", out)
        self.assertIn("Arguments only in removed branches: {name}", out)
        self.assertIn("Format-argument defects\n\nNone.", out)

    def test_apply_accepts_a_branch_collapse_without_a_flag(self):
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code, out, err = run(
                "apply",
                "--app",
                str(self.app),
                "--target",
                str(self.root / "Collapsed.app"),
                "--catalog-dir",
                str(self._branch_collapsing_catalog()),
            )
        self.assertEqual(code, EXIT_OK, err)
        self.assertIn("branch collapse", out)
        self.assertTrue((self.root / "Collapsed.app").is_dir())

    def test_apply_and_lint_agree_on_a_defect(self):
        """There is no path by which a visible defect reaches an install."""
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            apply_code, _, apply_err = run(
                "apply",
                "--app",
                str(self.app),
                "--target",
                str(self.root / "Defect.app"),
                "--catalog-dir",
                str(self._bad_catalog()),
            )
        lint_code, lint_out, _ = run(
            "lint", "--app", str(self.app), "--catalog-dir", str(self._bad_catalog())
        )
        self.assertEqual(apply_code, EXIT_CATALOG)
        self.assertEqual(lint_code, EXIT_CATALOG)
        self.assertIn("format argument", apply_err)
        self.assertIn("Not installable", lint_out)
        self.assertFalse((self.root / "Defect.app").exists())


class ScanCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_clean_tree_returns_zero(self):
        (self.root / "notes.md").write_text("nothing to see\n", encoding="utf-8")
        code, out, _ = run("scan", str(self.root))
        self.assertEqual(code, EXIT_OK)
        self.assertIn("0 error(s)", out)

    def test_planted_secret_returns_one(self):
        (self.root / "leak.txt").write_text(
            "key=" + "sk-ant-" + "R" * 28, encoding="utf-8"
        )
        code, out, _ = run("scan", str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("anthropic-api-key", out)

    def test_json_output(self):
        (self.root / "leak.txt").write_text(
            "key=" + "sk-ant-" + "R" * 28, encoding="utf-8"
        )
        code, out, _ = run("--json", "scan", str(self.root))
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["errors"], 1)
        self.assertEqual(payload["findings"][0]["rule"], "anthropic-api-key")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
