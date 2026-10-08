"""Tests for verification and rollback of an installed copy."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from claude_zh_patch import catalog as catalog_mod, lifecycle, patcher
from claude_zh_patch.errors import PatchError

from . import support

RESTRICTED = (
    "com.apple.application-identifier",
    "com.apple.developer.team-identifier",
    "keychain-access-groups",
)


class LifecycleTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.addCleanup(support.unregister_version, support.SYNTHETIC_VERSION)

    def install(self, *, entitlements=None) -> Path:
        app = support.build_app(self.root, name="Source.app")
        support.register_version(support.SYNTHETIC_VERSION, app)
        directory = support.build_catalog(self.root)
        loaded = catalog_mod.load_catalog(directory)
        target = self.root / "Installed.app"
        ents = {"com.apple.security.cs.allow-jit": True} if entitlements is None else entitlements
        with support.FakeSigning(ents):
            patcher.apply(app, target, loaded)
        return target


class VerifyTests(LifecycleTestCase):
    def test_a_freshly_installed_copy_verifies(self):
        target = self.install()
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            report = lifecycle.verify(target)
        self.assertTrue(report.ok)
        self.assertTrue(report.signature_ok)
        self.assertTrue(report.digest_matches)
        self.assertTrue(all(report.locale_files.values()))
        self.assertEqual(report.restricted_entitlements, ())

    def test_verify_reports_the_catalog_licence_and_origin(self):
        target = self.install()
        with support.FakeSigning():
            report = lifecycle.verify(target)
        self.assertEqual(report.catalog["license"], "CC0-1.0 (test fixture)")
        self.assertEqual(report.catalog["origin"], "written for the test suite")

    def test_verify_refuses_a_bundle_without_a_marker(self):
        plain = support.build_app(self.root, name="Plain.app")
        with self.assertRaises(PatchError) as caught:
            lifecycle.verify(plain)
        self.assertIn("marker", str(caught.exception))

    def test_verify_refuses_a_missing_bundle(self):
        with self.assertRaises(PatchError):
            lifecycle.verify(self.root / "Absent.app")

    def test_verify_detects_a_tampered_catalog(self):
        target = self.install()
        i18n = target / "Contents/Resources/ion-dist/i18n"
        payload = json.loads((i18n / "zh-Hans.json").read_text(encoding="utf-8"))
        payload["signIn"] = "tampered"
        (i18n / "zh-Hans.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        with support.FakeSigning():
            report = lifecycle.verify(target)
        self.assertFalse(report.digest_matches)
        self.assertFalse(report.ok)

    def test_verify_detects_a_missing_locale_file(self):
        target = self.install()
        (target / "Contents/Resources/ion-dist/i18n/zh-CN.json").unlink()
        with support.FakeSigning():
            report = lifecycle.verify(target)
        self.assertFalse(report.locale_files["zh-CN.json"])
        self.assertFalse(report.ok)

    def test_verify_flags_restricted_entitlements_left_behind(self):
        target = self.install()
        leftover = {
            "com.apple.security.cs.allow-jit": True,
            "keychain-access-groups": ["Q6L2SF6YDW.com.example"],
        }
        with support.FakeSigning(leftover):
            report = lifecycle.verify(target)
        self.assertIn("keychain-access-groups", report.restricted_entitlements)
        self.assertFalse(report.ok, "a copy carrying a team-scoped entitlement is not OK")

    def test_verify_refuses_a_marker_from_a_future_schema(self):
        target = self.install()
        marker_path = target / "Contents/Resources/CLAUDE_ZH3P_PATCH_INFO.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["schemaVersion"] = 99
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
        with self.assertRaises(PatchError) as caught:
            lifecycle.verify(target)
        self.assertIn("schema", str(caught.exception))

    def test_verify_reports_a_version_disagreement(self):
        target = self.install()
        marker_path = target / "Contents/Resources/CLAUDE_ZH3P_PATCH_INFO.json"
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["sourceVersion"] = "0.0.0-other"
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
        with self.assertRaises(PatchError) as caught:
            lifecycle.verify(target)
        self.assertIn("marker says", str(caught.exception))


class RollbackTests(LifecycleTestCase):
    def test_rollback_moves_the_copy_to_the_given_trash(self):
        target = self.install()
        trash = self.root / "Trash"
        destination = lifecycle.rollback(target, trash=trash)
        self.assertFalse(target.exists())
        self.assertTrue(destination.is_dir())
        self.assertTrue(destination.name.startswith("Installed.app.rolled-back-"))
        self.assertEqual(destination.parent, trash)

    def test_rollback_is_reversible_from_the_destination(self):
        target = self.install()
        trash = self.root / "Trash"
        destination = lifecycle.rollback(target, trash=trash)
        self.assertTrue(
            (destination / "Contents/Resources/CLAUDE_ZH3P_PATCH_INFO.json").is_file()
        )

    def test_rollback_refuses_a_bundle_without_a_marker(self):
        plain = support.build_app(self.root, name="Official-ish.app")
        with self.assertRaises(PatchError) as caught:
            lifecycle.rollback(plain, trash=self.root / "Trash")
        self.assertIn("marker", str(caught.exception))
        self.assertTrue(plain.is_dir(), "the refused bundle must be left alone")

    def test_rollback_refuses_something_that_is_not_an_app(self):
        directory = self.root / "NotAnApp"
        directory.mkdir()
        with self.assertRaises(PatchError) as caught:
            lifecycle.rollback(directory, trash=self.root / "Trash")
        self.assertIn(".app", str(caught.exception))

    def test_rollback_refuses_a_missing_path(self):
        with self.assertRaises(PatchError):
            lifecycle.rollback(self.root / "Absent.app", trash=self.root / "Trash")

    def test_rollback_does_not_collide_on_repeated_runs(self):
        trash = self.root / "Trash"
        first = lifecycle.rollback(self.install(), trash=trash)

        second_app = support.build_app(self.root, name="Source.app")
        support.register_version(support.SYNTHETIC_VERSION, second_app)
        directory = support.build_catalog(self.root)
        loaded = catalog_mod.load_catalog(directory)
        target = self.root / "Installed.app"
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            patcher.apply(second_app, target, loaded)
            second = lifecycle.rollback(target, trash=trash)

        self.assertNotEqual(first, second)
        self.assertTrue(first.is_dir() and second.is_dir())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
