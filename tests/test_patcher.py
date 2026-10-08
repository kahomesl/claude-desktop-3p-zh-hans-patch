"""Tests for plan construction, refusals and the apply pipeline.

The pipeline runs against a synthetic bundle with code signing stubbed out, so
these tests are hermetic. Real signing is covered by
``test_integration_reference.py``.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from claude_zh_patch import bundle, catalog as catalog_mod, compat, patcher
from claude_zh_patch.errors import (
    CatalogError,
    IncompatibleBundleError,
    PatchError,
)
from claude_zh_patch.signing import SigningError

from . import support


class PatcherTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        # The reference entitlement set, so plan reporting has something real.
        self.entitlements = {key: True for key in (
            "com.apple.application-identifier",
            "com.apple.developer.team-identifier",
            "com.apple.security.cs.allow-jit",
            "keychain-access-groups",
        )}
        self.addCleanup(support.unregister_version, support.SYNTHETIC_VERSION)

    def make_app(self, **kwargs) -> Path:
        app = support.build_app(self.root, **kwargs)
        support.register_version(kwargs.get("version", support.SYNTHETIC_VERSION), app)
        return app

    def make_catalog(self, **kwargs) -> catalog_mod.Catalog:
        directory = support.build_catalog(self.root, **kwargs)
        return catalog_mod.load_catalog(directory)


class BuildPlanTests(PatcherTestCase):
    def test_plan_covers_the_three_rewrite_targets(self):
        app = self.make_app()
        with support.FakeSigning(self.entitlements):
            plan = patcher.build_plan(app)
        self.assertEqual(
            sorted(plan.filenames),
            sorted((support.MAIN_ASSET, support.PICKER_ASSET, support.OFFER_ASSET)),
        )

    def test_rewrite_replaces_the_allowlist_and_the_picker(self):
        app = self.make_app()
        with support.FakeSigning(self.entitlements):
            plan = patcher.build_plan(app)

        main = next(text for path, text in plan.rewrites.items() if path.name == support.MAIN_ASSET)
        self.assertNotIn(compat.EN_ALLOWLIST, main)
        self.assertIn(compat.ZH_ALLOWLIST, main)

        picker = next(
            text for path, text in plan.rewrites.items() if path.name == support.PICKER_ASSET
        )
        self.assertNotIn(compat.PICKER_NAME_ANCHOR, picker)
        self.assertIn(compat.PICKER_NAME_PATCH, picker)

    def test_occurrence_drift_is_refused(self):
        app = self.make_app(allowlist_occurrences=1)
        with support.FakeSigning(self.entitlements):
            with self.assertRaises(IncompatibleBundleError) as caught:
                patcher.build_plan(app)
        self.assertIn("expected exactly 2", caught.exception.message)

    def test_missing_target_file_is_refused(self):
        app = self.make_app(omit_asset=support.PICKER_ASSET)
        with support.FakeSigning(self.entitlements):
            with self.assertRaises(IncompatibleBundleError):
                patcher.build_plan(app)

    def test_stray_allowlist_elsewhere_is_refused(self):
        app = self.make_app(stray_allowlist=True)
        with support.FakeSigning(self.entitlements):
            with self.assertRaises(IncompatibleBundleError) as caught:
                patcher.build_plan(app)
        self.assertIn("asset tree", caught.exception.message)

    def test_digest_mismatch_is_refused(self):
        app = self.make_app()
        assets = app / "Contents/Resources/ion-dist/assets/v1"
        # Rewrite a target file without changing its anchor counts, then re-record
        # digests so that only the digest check can catch it.
        (assets / support.OFFER_ASSET).write_text(
            f"/*tampered*/{compat.PICKER_OFFER_ANCHOR}/*end*/", encoding="utf-8"
        )
        with support.FakeSigning(self.entitlements):
            with self.assertRaises(IncompatibleBundleError) as caught:
                patcher.build_plan(app)
        self.assertIn("digest mismatch", caught.exception.message)

    def test_already_patched_bundle_is_refused(self):
        app = self.make_app(already_patched=True)
        with support.FakeSigning(self.entitlements):
            with self.assertRaises(IncompatibleBundleError) as caught:
                patcher.build_plan(app)
        self.assertIn("already", caught.exception.message)

    def test_unsupported_version_is_refused_before_any_structure_work(self):
        app = support.build_app(self.root, version="9.9.9-unknown", name="Other.app")
        with self.assertRaises(Exception) as caught:
            patcher.build_plan(app)
        self.assertEqual(getattr(caught.exception, "exit_code", None), 3)

    def test_plan_reports_the_entitlement_change(self):
        app = self.make_app()
        with support.FakeSigning(self.entitlements):
            plan = patcher.build_plan(app)
        self.assertEqual(
            plan.removed_entitlements,
            (
                "com.apple.application-identifier",
                "com.apple.developer.team-identifier",
                "keychain-access-groups",
            ),
        )
        self.assertEqual(
            plan.added_entitlements, ("com.apple.security.cs.disable-library-validation",)
        )


class ApplyTests(PatcherTestCase):
    def _apply(self, app, catalog, target=None, **kwargs):
        target = target or (self.root / "Out.app")
        with support.FakeSigning(self.entitlements):
            return patcher.apply(app, target, catalog, sign=support.fake_signer, **kwargs)

    def test_apply_produces_a_copy_that_verifies(self):
        app = self.make_app()
        result = self._apply(app, self.make_catalog())
        self.assertTrue(result.target.is_dir())
        self.assertTrue(result.signing.verified)

    def test_apply_writes_the_target_language_files(self):
        app = self.make_app()
        result = self._apply(app, self.make_catalog())
        i18n = result.target / "Contents/Resources/ion-dist/i18n"
        for name in ("zh-Hans.json", "zh-CN.json", "dynamic/zh-Hans.json", "zh-Hans.overrides.json"):
            with self.subTest(name=name):
                self.assertTrue((i18n / name).is_file(), name)
        installed = json.loads((i18n / "zh-Hans.json").read_text(encoding="utf-8"))
        self.assertEqual(installed["signIn"], "登录")

    def test_apply_rewrites_the_javascript(self):
        from claude_zh_patch import compat

        app = self.make_app()
        result = self._apply(app, self.make_catalog())
        assets = result.target / "Contents/Resources/ion-dist/assets/v1"
        main = (assets / support.MAIN_ASSET).read_text(encoding="utf-8")
        self.assertIn(compat.ZH_ALLOWLIST, main)
        self.assertNotIn(compat.EN_ALLOWLIST, main)

    def test_marker_has_no_paths_and_records_the_catalog(self):
        app = self.make_app()
        result = self._apply(app, self.make_catalog())
        marker = json.loads(
            (result.target / "Contents/Resources/CLAUDE_ZH3P_PATCH_INFO.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(marker["patch"], patcher.MARKER_PATCH_ID)
        self.assertEqual(marker["sourceVersion"], support.SYNTHETIC_VERSION)
        self.assertEqual(marker["catalog"]["excusedBranchCollapses"], 0)
        rendered = json.dumps(marker)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(str(Path.home()), rendered)

    def test_apply_refuses_an_existing_target(self):
        app = self.make_app()
        target = self.root / "Out.app"
        target.mkdir()
        with self.assertRaises(PatchError) as caught:
            self._apply(app, self.make_catalog(), target=target)
        self.assertIn("already exists", caught.exception.message)

    def test_apply_refuses_in_place(self):
        app = self.make_app()
        with self.assertRaises(PatchError) as caught:
            self._apply(app, self.make_catalog(), target=app)
        self.assertIn("in place", caught.exception.message)

    def test_apply_refuses_an_undercovered_catalog(self):
        app = self.make_app()
        catalog = self.make_catalog(base={"greeting": "您好，{name}！"})
        with self.assertRaises(CatalogError) as caught:
            self._apply(app, catalog)
        self.assertIn("coverage", str(caught.exception))

    def test_apply_refuses_a_visible_argument_defect(self):
        app = self.make_app()
        base = {
            "greeting": "您好！",  # {name} dropped, and it renders outside every branch
            "itemCount": "{count, plural, other {# 项}}",
            "signIn": "登录",
            "signOut": "退出登录",
            "saved": "已保存 {fileName}",
            "deleted": "已删除 1 个{noun}",
            "retry": "重试",
            "settings": "设置",
            "sharedWith": "{count, plural, one {{name} 共享了此内容} other {{names} 共享了此内容}}",
        }
        with self.assertRaises(CatalogError) as caught:
            self._apply(app, self.make_catalog(base=base))
        self.assertIn("format argument", str(caught.exception))

    def test_apply_accepts_a_branch_collapse_without_a_flag(self):
        """A language that does not inflect must install with no override."""
        app = self.make_app()
        base = {
            "greeting": "您好，{name}！",
            "itemCount": "{count, plural, other {# 项}}",
            "signIn": "登录",
            "signOut": "退出登录",
            "saved": "已保存 {fileName}",
            "deleted": "已删除 1 个{noun}",
            "retry": "重试",
            "settings": "设置",
            # Only the plural branch, so {name} goes with the removed one.
            "sharedWith": "{count, plural, other {{names} 共享了此内容}}",
        }
        result = self._apply(app, self.make_catalog(base=base))
        self.assertTrue(result.target.is_dir())
        self.assertEqual(result.excused_branch_collapses, 1)

        marker = json.loads(
            (result.target / "Contents/Resources/CLAUDE_ZH3P_PATCH_INFO.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(marker["catalog"]["excusedBranchCollapses"], 1)

    def test_apply_still_refuses_a_defect_alongside_a_collapse(self):
        """An accepted collapse must not carry a visible defect in with it."""
        app = self.make_app()
        base = {
            "greeting": "您好！",  # a visible defect
            "itemCount": "{count, plural, other {# 项}}",
            "signIn": "登录",
            "signOut": "退出登录",
            "saved": "已保存 {fileName}",
            "deleted": "已删除 1 个{noun}",
            "retry": "重试",
            "settings": "设置",
            "sharedWith": "{count, plural, other {{names} 共享了此内容}}",  # a collapse
        }
        with self.assertRaises(CatalogError):
            self._apply(app, self.make_catalog(base=base))
        self.assertFalse((self.root / "Out.app").exists())

    def test_apply_refuses_when_the_source_signature_is_invalid(self):
        app = self.make_app()
        catalog = self.make_catalog()
        with mock.patch(
            "claude_zh_patch.bundle.verify_signature", return_value=(False, "bad seal")
        ):
            with self.assertRaises(IncompatibleBundleError) as caught:
                patcher.apply(app, self.root / "Out.app", catalog, sign=support.fake_signer)
        self.assertIn("does not verify", caught.exception.message)

    def test_a_failed_signing_step_leaves_no_partial_copy(self):
        app = self.make_app()
        catalog = self.make_catalog()
        target = self.root / "Out.app"

        def exploding_signer(_target):
            raise SigningError("no identity available")

        with support.FakeSigning(self.entitlements):
            with self.assertRaises(SigningError):
                patcher.apply(app, target, catalog, sign=exploding_signer)
        self.assertFalse(target.exists(), "a partial copy must be cleaned up")

    def test_the_source_bundle_is_never_modified(self):
        app = self.make_app()
        before = {
            path: path.read_bytes()
            for path in app.rglob("*")
            if path.is_file()
        }
        self._apply(app, self.make_catalog())
        after = {path: path.read_bytes() for path in app.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_check_source_reports_the_plan(self):
        app = self.make_app()
        with support.FakeSigning(self.entitlements):
            report = patcher.check_source(app)
        self.assertEqual(report["version"], support.SYNTHETIC_VERSION)
        self.assertIsInstance(report["plan"], patcher.PatchPlan)


class CheckSourceIsReadOnlyTests(PatcherTestCase):
    def test_check_source_writes_nothing(self):
        app = self.make_app()
        before = sorted(str(p.relative_to(app)) for p in app.rglob("*"))
        with support.FakeSigning(self.entitlements):
            patcher.check_source(app)
        after = sorted(str(p.relative_to(app)) for p in app.rglob("*"))
        self.assertEqual(before, after)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
