"""Tests for the ad-hoc signing logic.

The central claim of this module is that an ad-hoc signature must not carry the
restricted identity entitlements the original Developer ID build had. The test
below pins that claim to the exact entitlement sets observed on disk, so a future
edit that starts preserving them again fails here.
"""

from __future__ import annotations

import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from claude_zh_patch import signing

#: The entitlement keys carried by the reference Developer ID build.
OFFICIAL_ENTITLEMENT_KEYS = (
    "com.apple.application-identifier",
    "com.apple.developer.team-identifier",
    "com.apple.security.automation.apple-events",
    "com.apple.security.cs.allow-jit",
    "com.apple.security.device.audio-input",
    "com.apple.security.device.bluetooth",
    "com.apple.security.device.camera",
    "com.apple.security.device.print",
    "com.apple.security.device.usb",
    "com.apple.security.personal-information.location",
    "com.apple.security.personal-information.photos-library",
    "com.apple.security.virtualization",
    "keychain-access-groups",
)

#: What must be removed: everything bound to a team identity or provisioning
#: profile, none of which an ad-hoc signature can substantiate.
EXPECTED_RESTRICTED = (
    "com.apple.application-identifier",
    "com.apple.developer.team-identifier",
    "keychain-access-groups",
)

#: The entitlement an ad-hoc signed Electron bundle needs in their place.
EXPECTED_ADDED = ("com.apple.security.cs.disable-library-validation",)


def _official() -> dict:
    return {key: True for key in OFFICIAL_ENTITLEMENT_KEYS}


class StripRestrictedTests(unittest.TestCase):
    def test_removes_exactly_the_restricted_identity_entitlements(self):
        kept, removed = signing.strip_restricted(_official())
        self.assertEqual(tuple(removed), EXPECTED_RESTRICTED)
        self.assertEqual(
            sorted(kept), sorted(set(OFFICIAL_ENTITLEMENT_KEYS) - set(EXPECTED_RESTRICTED))
        )

    def test_every_kept_entitlement_is_a_hardened_runtime_entitlement(self):
        kept, _ = signing.strip_restricted(_official())
        for key in kept:
            with self.subTest(key=key):
                self.assertTrue(key.startswith("com.apple.security."))

    def test_removal_preserves_values_of_kept_entitlements(self):
        entitlements = dict(_official())
        entitlements["com.apple.security.cs.allow-jit"] = False
        kept, _ = signing.strip_restricted(entitlements)
        self.assertIs(kept["com.apple.security.cs.allow-jit"], False)

    def test_any_developer_prefixed_key_is_restricted(self):
        kept, removed = signing.strip_restricted(
            {"com.apple.developer.usernotifications.filtering": True, "com.apple.security.cs.allow-jit": True}
        )
        self.assertEqual(removed, ["com.apple.developer.usernotifications.filtering"])
        self.assertEqual(list(kept), ["com.apple.security.cs.allow-jit"])

    def test_empty_input(self):
        kept, removed = signing.strip_restricted({})
        self.assertEqual(kept, {})
        self.assertEqual(removed, [])

    def test_is_restricted_matches_the_strip_rule(self):
        for key in EXPECTED_RESTRICTED:
            with self.subTest(key=key):
                self.assertTrue(signing.is_restricted(key))
        self.assertTrue(signing.is_restricted("com.apple.developer.anything"))
        self.assertFalse(signing.is_restricted("com.apple.security.cs.allow-jit"))
        self.assertFalse(signing.is_restricted("com.apple.security.device.camera"))


class PlanMainEntitlementsTests(unittest.TestCase):
    def test_produces_the_verified_entitlement_set(self):
        final, removed, added = signing.plan_main_entitlements(_official())
        self.assertEqual(tuple(removed), EXPECTED_RESTRICTED)
        self.assertEqual(tuple(added), EXPECTED_ADDED)
        self.assertEqual(len(final), len(OFFICIAL_ENTITLEMENT_KEYS) - len(EXPECTED_RESTRICTED) + 1)
        self.assertNotIn("keychain-access-groups", final)
        self.assertNotIn("com.apple.application-identifier", final)
        self.assertNotIn("com.apple.developer.team-identifier", final)
        self.assertTrue(final["com.apple.security.cs.disable-library-validation"])
        for key in EXPECTED_RESTRICTED:
            self.assertNotIn(key, final)

    def test_no_restricted_key_survives(self):
        final, _, _ = signing.plan_main_entitlements(_official())
        for key in final:
            with self.subTest(key=key):
                self.assertFalse(signing.is_restricted(key))

    def test_disable_library_validation_is_not_reported_as_added_twice(self):
        entitlements = dict(_official())
        entitlements["com.apple.security.cs.disable-library-validation"] = True
        _, _, added = signing.plan_main_entitlements(entitlements)
        self.assertEqual(added, [])

    def test_none_input(self):
        final, removed, added = signing.plan_main_entitlements(None)
        self.assertEqual(final, dict(signing.ADHOC_REQUIRED_ENTITLEMENTS))
        self.assertEqual(removed, [])
        self.assertEqual(tuple(added), EXPECTED_ADDED)


class ReadEntitlementsTests(unittest.TestCase):
    def test_returns_none_when_codesign_reports_nothing(self):
        completed = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with mock.patch("claude_zh_patch.signing.subprocess.run", return_value=completed):
            self.assertIsNone(signing.read_entitlements(Path("/tmp/whatever")))

    def test_parses_a_plist_from_stdout(self):
        blob = plistlib.dumps({"com.apple.security.cs.allow-jit": True})
        completed = mock.Mock(returncode=0, stdout=blob, stderr=b"")
        with mock.patch("claude_zh_patch.signing.subprocess.run", return_value=completed):
            result = signing.read_entitlements(Path("/tmp/whatever"))
        self.assertEqual(result, {"com.apple.security.cs.allow-jit": True})

    def test_returns_none_for_an_unparseable_blob(self):
        completed = mock.Mock(returncode=0, stdout=b"<?xml not really", stderr=b"")
        with mock.patch("claude_zh_patch.signing.subprocess.run", return_value=completed):
            self.assertIsNone(signing.read_entitlements(Path("/tmp/whatever")))


class SignCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "Thing"

    def _captured_args(self, entitlements):
        completed = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with mock.patch("claude_zh_patch.signing.subprocess.run", return_value=completed) as run:
            signing._sign(self.path, entitlements)
        return run.call_args.args[0]

    def test_signs_ad_hoc_with_the_hardened_runtime(self):
        args = self._captured_args(None)
        self.assertIn("--force", args)
        self.assertIn("--sign", args)
        self.assertEqual(args[args.index("--sign") + 1], "-")
        self.assertEqual(args[args.index("--options") + 1], "runtime")
        self.assertIn("--timestamp=none", args)
        self.assertEqual(args[-1], str(self.path))
        self.assertNotIn("--entitlements", args)
        self.assertNotIn("--preserve-metadata", args)
        self.assertNotIn("--deep", args)

    def test_passes_entitlements_through_a_temporary_file(self):
        args = self._captured_args({"com.apple.security.cs.allow-jit": True})
        self.assertIn("--entitlements", args)
        path = Path(args[args.index("--entitlements") + 1])
        self.assertTrue(path.name.startswith("zh-patch-ent-"))
        self.assertFalse(path.exists(), "the temporary entitlement file must be removed")

    def test_failure_raises_with_stderr_detail(self):
        completed = mock.Mock(returncode=1, stdout=b"", stderr=b"err: something went wrong")
        with mock.patch("claude_zh_patch.signing.subprocess.run", return_value=completed):
            with self.assertRaises(signing.SigningError) as caught:
                signing._sign(self.path, None)
        self.assertIn("something went wrong", caught.exception.detail)


class CollectSignablesTests(unittest.TestCase):
    MACHO = b"\xcf\xfa\xed\xfe" + b"\x00" * 60

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = Path(self._tmp.name) / "Synthetic.app"
        self._write("Contents/MacOS/Synthetic")
        self._write("Contents/Frameworks/Helper.app/Contents/MacOS/Helper")
        self._write("Contents/Frameworks/Kernel.framework/Versions/A/Kernel")
        self._write("Contents/Resources/libextra.dylib")
        (self.app / "Contents/Resources/notes.txt").write_text("not code", encoding="utf-8")

    def _write(self, relative: str) -> None:
        path = self.app / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.MACHO)

    def test_finds_nested_bundles_and_loose_binaries(self):
        relatives = {str(p.relative_to(self.app)) for p in signing.collect_signables(self.app)}
        self.assertIn("Contents/Frameworks/Helper.app", relatives)
        self.assertIn("Contents/Frameworks/Kernel.framework", relatives)
        self.assertIn("Contents/MacOS/Synthetic", relatives)
        self.assertIn("Contents/Resources/libextra.dylib", relatives)

    def test_omits_binaries_that_a_nested_bundle_will_cover(self):
        relatives = {str(p.relative_to(self.app)) for p in signing.collect_signables(self.app)}
        self.assertNotIn("Contents/Frameworks/Helper.app/Contents/MacOS/Helper", relatives)
        self.assertNotIn(
            "Contents/Frameworks/Kernel.framework/Versions/A/Kernel", relatives
        )

    def test_ignores_non_code_files(self):
        relatives = {str(p.relative_to(self.app)) for p in signing.collect_signables(self.app)}
        self.assertNotIn("Contents/Resources/notes.txt", relatives)

    def test_deepest_items_come_first(self):
        items = signing.collect_signables(self.app)
        depths = [len(p.parts) for p in items]
        self.assertEqual(depths, sorted(depths, reverse=True))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
