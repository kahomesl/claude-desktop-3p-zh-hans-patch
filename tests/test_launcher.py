"""Tests for the double-click launcher.

Every scenario the launcher is expected to handle has a test here, and so do the
things it must never do: weaken the tool, overwrite something, escalate
privileges, or build a shell command out of user input.

The install path runs the real ``check``/``apply``/``verify`` commands against a
synthetic bundle, with code signing stubbed out, so these tests are hermetic.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claude_zh_patch import cli, launcher
from claude_zh_patch.errors import (
    EXIT_CATALOG,
    EXIT_OK,
    EXIT_UNSUPPORTED_VERSION,
)

from . import support

REPOSITORY = Path(__file__).resolve().parent.parent
COMMAND_FILE = REPOSITORY / "启动Claude中文版.command"


def quiet_cli(argv) -> int:
    """Run the real CLI with its output suppressed, as the launcher would."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            return cli.main(list(argv))
        except SystemExit as exc:
            return int(exc.code) if isinstance(exc.code, int) else 1


class Recorder:
    """A scripted console reader, so prompts never block a test."""

    def __init__(self, answers=()):
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0) if self.answers else ""


class LauncherTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(support.unregister_version, support.SYNTHETIC_VERSION)

        self.out = io.StringIO()
        self.err = io.StringIO()
        self.reader = Recorder()
        self.console = launcher.Console(self.out, self.err, read=self.reader)

        self.config = self.root / "config" / "config.json"
        self.calls: list[list[str]] = []

    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()

    def make_app(
        self,
        *,
        version=support.SYNTHETIC_VERSION,
        name="Source.app",
        register: bool = True,
    ) -> Path:
        app = support.build_app(self.root, version=version, name=name)
        if register:
            support.register_version(version, app)
        return app

    def make_catalog(self, name="catalog", **kwargs) -> Path:
        return support.build_catalog(self.root, name=name, **kwargs)

    def make_launcher(self, app: Path, **overrides) -> launcher.Launcher:
        def run_cli(argv):
            self.calls.append(list(argv))
            return quiet_cli(argv)

        kwargs = dict(
            console=self.console,
            config_path=self.config,
            source_app=app,
            default_target=self.root / "Default.app",
            run_cli=run_cli,
            pids=lambda: [],
            opener=lambda target: (True, ""),
            # The synthetic bundle is not code-signed; the real check is covered
            # by the integration test and by SignatureFailureTests below.
            verify_source=lambda path: (True, ""),
        )
        kwargs.update(overrides)
        return launcher.Launcher(**kwargs)


# ---------------------------------------------------------------------------
# 1. first install
# ---------------------------------------------------------------------------


class FirstInstallTests(LauncherTestCase):
    def test_first_run_installs_and_reports_success(self):
        app = self.make_app()
        catalog = self.make_catalog()
        target = self.root / "Out.app"
        machine = self.make_launcher(app)

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(catalog=catalog, target=target, launch=False)

        self.assertEqual(code, EXIT_OK, self.text())
        self.assertTrue(target.is_dir())
        self.assertIn("安装完成", self.text())
        self.assertIn("不会修改官方 Claude.app", self.text())

    def test_first_run_saves_configuration(self):
        app = self.make_app()
        catalog = self.make_catalog()
        target = self.root / "Out.app"
        machine = self.make_launcher(app)

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            machine.run(catalog=catalog, target=target, launch=False)

        self.assertTrue(self.config.is_file())
        saved = launcher.load_config(self.config)
        self.assertEqual(saved.catalog, catalog)
        self.assertEqual(saved.target, target)

    def test_steps_are_announced_in_order(self):
        app = self.make_app()
        catalog = self.make_catalog()
        machine = self.make_launcher(app)

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            machine.run(catalog=catalog, target=self.root / "Out.app", launch=False)

        text = self.text()
        for marker in ("[1/5]", "[2/5]", "[3/5]", "[4/5]"):
            self.assertIn(marker, text)

    def test_install_runs_check_then_apply_then_verify(self):
        app = self.make_app()
        catalog = self.make_catalog()
        machine = self.make_launcher(app)

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            machine.run(catalog=catalog, target=self.root / "Out.app", launch=False)

        subcommands = [call[0] for call in self.calls]
        self.assertEqual(subcommands, ["check", "apply", "verify"])


# ---------------------------------------------------------------------------
# 2. repeat launch
# ---------------------------------------------------------------------------


class RepeatRunTests(LauncherTestCase):
    def _install_once(self, app, catalog, target):
        machine = self.make_launcher(app)
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            machine.run(catalog=catalog, target=target, launch=False)
        return machine

    def test_second_run_verifies_instead_of_reinstalling(self):
        app = self.make_app()
        catalog = self.make_catalog()
        target = self.root / "Out.app"
        self._install_once(app, catalog, target)

        self.calls.clear()
        machine = self.make_launcher(app)
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(launch=False)

        self.assertEqual(code, EXIT_OK, self.text())
        self.assertIn("已存在的副本校验通过", self.text())
        self.assertEqual([call[0] for call in self.calls], ["verify"])
        self.assertNotIn("apply", [call[0] for call in self.calls])

    def test_second_run_uses_the_saved_catalog_without_prompting(self):
        app = self.make_app()
        catalog = self.make_catalog()
        target = self.root / "Out.app"
        self._install_once(app, catalog, target)

        machine = self.make_launcher(app)
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            machine.run(launch=False)

        self.assertEqual(self.reader.prompts, [], "should not have prompted at all")


# ---------------------------------------------------------------------------
# 3. incompatible version
# ---------------------------------------------------------------------------


class IncompatibleVersionTests(LauncherTestCase):
    def test_unsupported_version_stops_with_an_explanation(self):
        app = self.make_app(version="9.9.9-unknown", register=False)
        catalog = self.make_catalog()
        target = self.root / "Out.app"
        machine = self.make_launcher(app)

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(catalog=catalog, target=target, launch=False)

        self.assertEqual(code, EXIT_UNSUPPORTED_VERSION)
        text = self.text()
        self.assertIn("版本不受支持", text)
        self.assertIn("没有强制绕过", text)
        self.assertIn("从备份安装", text)
        self.assertFalse(target.exists(), "nothing may be written")

    def test_unsupported_version_is_not_reported_as_success(self):
        app = self.make_app(version="9.9.9-unknown", register=False)
        machine = self.make_launcher(app)
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(
                catalog=self.make_catalog(), target=self.root / "O.app", launch=False
            )
        self.assertNotEqual(code, EXIT_OK)


# ---------------------------------------------------------------------------
# 4. missing or invalid catalog
# ---------------------------------------------------------------------------


class CatalogTests(LauncherTestCase):
    def test_missing_catalog_prompts_again_until_one_works(self):
        app = self.make_app()
        broken = self.root / "broken-catalog"
        broken.mkdir()
        (broken / "catalog.json").write_text("{}", encoding="utf-8")
        good = self.make_catalog()

        chosen = [broken, good]
        machine = self.make_launcher(app, choose=lambda kind: chosen.pop(0))

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(target=self.root / "Out.app", launch=False)

        self.assertEqual(code, EXIT_OK, self.text())
        self.assertIn("不能用作语言资源", self.text())
        self.assertEqual(chosen, [], "should have used the second choice")

    def test_cancelling_the_picker_aborts_without_writing(self):
        app = self.make_app()
        target = self.root / "Out.app"
        machine = self.make_launcher(app, choose=lambda kind: None)

        code = machine.run(target=target, launch=False)

        self.assertNotEqual(code, EXIT_OK)
        self.assertIn("已取消", self.text())
        self.assertFalse(target.exists())

    def test_the_picker_explains_that_no_translation_data_ships(self):
        app = self.make_app()
        good = self.make_catalog()
        machine = self.make_launcher(app, choose=lambda kind: good)

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            machine.run(target=self.root / "Out.app", launch=False)

        self.assertIn("不包含任何中文翻译内容", self.text())

    def test_a_catalog_that_fails_the_cli_is_explained(self):
        app = self.make_app()
        thin = self.make_catalog(name="thin", base={"greeting": "您好，{name}！"})
        machine = self.make_launcher(app)

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(catalog=thin, target=self.root / "Out.app", launch=False)

        self.assertEqual(code, EXIT_CATALOG)
        self.assertIn("语言资源未通过校验", self.text())
        self.assertFalse((self.root / "Out.app").exists())


# ---------------------------------------------------------------------------
# 5. signature failure
# ---------------------------------------------------------------------------


class SignatureFailureTests(LauncherTestCase):
    def test_a_damaged_source_is_refused_before_anything_is_written(self):
        app = self.make_app()
        catalog = self.make_catalog()
        target = self.root / "Out.app"

        machine = self.make_launcher(
            app, verify_source=lambda path: (False, "bad seal")
        )
        code = machine.run(catalog=catalog, target=target, launch=False)

        self.assertNotEqual(code, EXIT_OK)
        text = self.text()
        self.assertIn("签名校验未通过", text)
        self.assertIn("重新安装一份干净的官方应用", text)
        self.assertFalse(target.exists())
        self.assertEqual(self.calls, [], "no CLI command should have run")

    def test_the_real_signature_check_is_wired_in_by_default(self):
        """Without an override the launcher must consult the real verifier."""
        app = self.make_app()
        machine = launcher.Launcher(
            console=self.console,
            config_path=self.config,
            source_app=app,
            run_cli=lambda argv: (self.calls.append(list(argv)), EXIT_OK)[1],
        )
        self.assertEqual(machine.verify_source.__module__, "claude_zh_patch.bundle")
        self.assertEqual(machine.verify_source.__name__, "verify_signature")

    def test_a_missing_source_app_is_explained(self):
        machine = self.make_launcher(self.root / "Absent.app")
        code = machine.run(catalog=self.make_catalog(), target=self.root / "O.app", launch=False)

        self.assertNotEqual(code, EXIT_OK)
        self.assertIn("没有找到官方应用", self.text())


# ---------------------------------------------------------------------------
# 6. paths with spaces and non-ASCII characters
# ---------------------------------------------------------------------------


class AwkwardPathTests(LauncherTestCase):
    def test_spaces_and_chinese_in_the_target_path(self):
        app = self.make_app()
        catalog = self.make_catalog()
        target = self.root / "中文 目录 带空格" / "Claude 中文版.app"
        target.parent.mkdir(parents=True)

        machine = self.make_launcher(app)
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(catalog=catalog, target=target, launch=False)

        self.assertEqual(code, EXIT_OK, self.text())
        self.assertTrue(target.is_dir())
        saved = launcher.load_config(self.config)
        self.assertEqual(saved.target, target)

    def test_spaces_and_chinese_in_the_catalog_path(self):
        app = self.make_app()
        catalog = support.build_catalog(self.root, name="语言 资源 目录")
        machine = self.make_launcher(app)

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(catalog=catalog, target=self.root / "Out.app", launch=False)

        self.assertEqual(code, EXIT_OK, self.text())
        self.assertEqual(launcher.load_config(self.config).catalog, catalog)

    def test_arguments_are_passed_as_lists_not_shell_strings(self):
        """Awkward paths reach the CLI as single argv elements, never as text
        spliced into a command line."""
        app = self.make_app()
        catalog = support.build_catalog(self.root, name="a b c")
        target = self.root / "Out dir 带空格" / "Out.app"
        target.parent.mkdir()

        machine = self.make_launcher(app)
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            machine.run(catalog=catalog, target=target, launch=False)

        by_command = {call[0]: call for call in self.calls}
        self.assertEqual(sorted(by_command), ["apply", "check", "verify"])

        for command, call in by_command.items():
            with self.subTest(command=command):
                self.assertIsInstance(call, list)
                self.assertTrue(
                    all(isinstance(element, str) for element in call),
                    "every argv element must be a plain string",
                )

        for command in ("check", "apply"):
            with self.subTest(command=command):
                call = by_command[command]
                self.assertEqual(call[call.index("--catalog-dir") + 1], str(catalog))

        call = by_command["verify"]
        self.assertEqual(call[call.index("--target") + 1], str(target))


# ---------------------------------------------------------------------------
# 7. an existing target
# ---------------------------------------------------------------------------


class ExistingTargetTests(LauncherTestCase):
    def test_a_foreign_bundle_is_never_overwritten(self):
        app = self.make_app()
        catalog = self.make_catalog()
        target = self.root / "Someone Elses.app"
        (target / "Contents").mkdir(parents=True)
        (target / "Contents" / "marker.txt").write_text("do not touch", encoding="utf-8")

        machine = self.make_launcher(app)
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(catalog=catalog, target=target, launch=False)

        self.assertNotEqual(code, EXIT_OK)
        self.assertIn("不会覆盖", self.text())
        self.assertIn("rollback", self.text())
        self.assertEqual(
            (target / "Contents" / "marker.txt").read_text(encoding="utf-8"),
            "do not touch",
            "the existing bundle must be untouched",
        )
        self.assertFalse(
            (target / "Contents" / "CLAUDE_ZH3P_PATCH_INFO.json").exists()
        )

    def test_apply_is_never_called_against_an_existing_target(self):
        app = self.make_app()
        catalog = self.make_catalog()
        target = self.root / "Existing.app"
        target.mkdir()

        machine = self.make_launcher(app)
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            machine.run(catalog=catalog, target=target, launch=False)

        self.assertNotIn("apply", [call[0] for call in self.calls])


# ---------------------------------------------------------------------------
# target validation
# ---------------------------------------------------------------------------


class TargetValidationTests(unittest.TestCase):
    def test_the_official_app_is_refused(self):
        with self.assertRaises(launcher.LauncherAbort) as caught:
            launcher.validate_target(Path("/Applications/Claude.app"))
        self.assertIn("官方应用本身", str(caught.exception))

    def test_a_path_inside_the_official_app_is_refused(self):
        with self.assertRaises(launcher.LauncherAbort):
            launcher.validate_target(Path("/Applications/Claude.app/Contents/Nested.app"))

    def test_system_directories_are_refused(self):
        for path in ("/System/Thing.app", "/usr/local/Thing.app", "/Library/Thing.app"):
            with self.subTest(path=path):
                with self.assertRaises(launcher.LauncherAbort):
                    launcher.validate_target(Path(path))

    def test_a_non_app_path_is_refused(self):
        with self.assertRaises(launcher.LauncherAbort) as caught:
            launcher.validate_target(Path("/tmp/not-an-app"))
        self.assertIn(".app", str(caught.exception))

    def test_an_ordinary_user_path_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            launcher.validate_target(Path(tmp) / "Fine.app")

    def test_the_default_target_is_under_the_home_directory(self):
        """So that installing needs no administrator rights."""
        self.assertEqual(launcher.DEFAULT_TARGET.parent, Path.home() / "Applications")

    def test_tmp_is_not_treated_as_a_system_directory(self):
        """``/tmp`` resolves into ``/private``; rejecting it would be a false positive."""
        with tempfile.TemporaryDirectory() as tmp:
            launcher.validate_target(Path(tmp) / "Fine.app")


# ---------------------------------------------------------------------------
# launching
# ---------------------------------------------------------------------------


class LaunchTests(LauncherTestCase):
    def _installed(self, **overrides):
        app = self.make_app()
        catalog = self.make_catalog()
        target = self.root / "Out.app"
        machine = self.make_launcher(app, **overrides)
        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            machine.run(catalog=catalog, target=target, launch=False)
        return machine, target

    def test_launch_warns_about_running_instances_and_does_not_kill_them(self):
        opened: list[Path] = []
        machine, target = self._installed(
            pids=lambda: [101, 202],
            opener=lambda t: (opened.append(t), (True, ""))[1],
        )
        self.reader.answers = ["y"]

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(launch=True)

        self.assertEqual(code, EXIT_OK, self.text())
        text = self.text()
        self.assertIn("检测到 2 个正在运行的 Claude 进程", text)
        self.assertIn("不会替你结束进程", text)
        self.assertEqual(opened, [target])

    def test_declining_the_launch_does_not_open_anything(self):
        opened: list[Path] = []
        machine, _ = self._installed(
            opener=lambda t: (opened.append(t), (True, ""))[1]
        )
        self.reader.answers = ["n"]

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(launch=True)

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(opened, [])
        self.assertIn("没有启动", self.text())

    def test_a_failed_launch_is_reported_not_swallowed(self):
        machine, target = self._installed(opener=lambda t: (False, "killed: 9"))
        self.reader.answers = ["y"]

        with support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            code = machine.run(launch=True)

        self.assertNotEqual(code, EXIT_OK)
        self.assertIn("启动失败", self.text())
        self.assertIn("killed: 9", self.text())


# ---------------------------------------------------------------------------
# configuration file
# ---------------------------------------------------------------------------


class ConfigFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.path = self.root / "cfg" / "config.json"

    def test_file_mode_is_600_and_directory_is_700(self):
        launcher.save_config(
            launcher.Config(catalog=self.root / "c", target=self.root / "t.app"),
            self.path,
        )
        file_mode = stat.S_IMODE(self.path.stat().st_mode)
        dir_mode = stat.S_IMODE(self.path.parent.stat().st_mode)
        self.assertEqual(oct(file_mode), oct(0o600))
        self.assertEqual(oct(dir_mode), oct(0o700))

    def test_no_group_or_other_bits_are_set(self):
        launcher.save_config(
            launcher.Config(catalog=self.root / "c", target=self.root / "t.app"),
            self.path,
        )
        mode = self.path.stat().st_mode
        self.assertFalse(mode & stat.S_IRGRP)
        self.assertFalse(mode & stat.S_IROTH)

    def test_the_config_holds_only_the_two_paths(self):
        launcher.save_config(
            launcher.Config(catalog=self.root / "c", target=self.root / "t.app"),
            self.path,
        )
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(data), ["catalogPath", "schemaVersion", "targetApp"])

    def test_the_config_holds_no_language_data(self):
        catalog = self.root / "c"
        catalog.mkdir()
        (catalog / "base.json").write_text(
            json.dumps({"greeting": "机密译文 {name}"}, ensure_ascii=False), encoding="utf-8"
        )
        launcher.save_config(
            launcher.Config(catalog=catalog, target=self.root / "t.app"), self.path
        )
        rendered = self.path.read_text(encoding="utf-8")
        self.assertNotIn("机密译文", rendered)
        self.assertNotIn("{name}", rendered)

    def test_the_config_holds_no_credential_shaped_keys(self):
        launcher.save_config(
            launcher.Config(catalog=self.root / "c", target=self.root / "t.app"),
            self.path,
        )
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for key in data:
            lowered = key.lower()
            for forbidden in ("token", "secret", "key", "password", "cookie", "auth"):
                self.assertNotIn(forbidden, lowered, key)

    def test_a_missing_config_reads_as_none(self):
        self.assertIsNone(launcher.load_config(self.path))

    def test_a_corrupt_config_reads_as_none(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(launcher.load_config(self.path))

    def test_a_config_from_a_future_schema_reads_as_none(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"schemaVersion": 99, "catalogPath": "/a", "targetApp": "/b.app"}),
            encoding="utf-8",
        )
        self.assertIsNone(launcher.load_config(self.path))

    def test_a_config_with_empty_paths_reads_as_none(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"schemaVersion": 1, "catalogPath": "", "targetApp": "x.app"}),
            encoding="utf-8",
        )
        self.assertIsNone(launcher.load_config(self.path))


# ---------------------------------------------------------------------------
# the things it must never do
# ---------------------------------------------------------------------------


class AtomicConfigTests(unittest.TestCase):
    setUp = ConfigFileTests.setUp

    def save(self):
        return launcher.save_config(launcher.Config(self.root / "c", self.root / "t.app"), self.path)

    def test_private_existing_config_updates_atomically(self):
        self.save()
        old_inode = self.path.stat().st_ino
        self.save()
        self.assertNotEqual(old_inode, self.path.stat().st_ino)

    def test_foreign_file_and_wide_directory_are_untouched(self):
        self.path.parent.mkdir(mode=0o700)
        self.path.write_text("foreign", encoding="utf-8")
        self.path.chmod(0o600)
        with self.assertRaises(OSError):
            self.save()
        self.assertEqual(self.path.read_text(), "foreign")
        self.path.unlink()
        self.path.parent.chmod(0o755)
        with self.assertRaises(OSError):
            self.save()
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o755)

    def test_symlink_directory_and_file_are_refused(self):
        destination = self.root / "destination"
        destination.mkdir(mode=0o700)
        self.path.parent.symlink_to(destination, target_is_directory=True)
        with self.assertRaises(OSError):
            self.save()
        self.path.parent.unlink()
        self.path.parent.mkdir(mode=0o700)
        victim = self.root / "victim"
        victim.write_text("safe")
        self.path.symlink_to(victim)
        with self.assertRaises(OSError):
            self.save()
        self.assertEqual(victim.read_text(), "safe")

    def test_hardlink_fifo_and_wide_file_are_refused(self):
        self.save()
        os.link(self.path, self.root / "link")
        with self.assertRaises(OSError):
            self.save()
        (self.root / "link").unlink()
        self.path.chmod(0o644)
        with self.assertRaises(OSError):
            self.save()
        self.path.unlink()
        os.mkfifo(self.path, 0o600)
        with self.assertRaises(OSError):
            self.save()

    def test_failed_replace_preserves_old_file_and_cleans_temporary(self):
        self.save()
        before = self.path.read_bytes()
        with patch.object(launcher.os, "replace", side_effect=OSError("failed")):
            with self.assertRaises(OSError):
                self.save()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_destination_change_before_replace_is_refused(self):
        self.save()
        real_fsync = os.fsync
        def change(fd):
            real_fsync(fd)
            self.path.write_text("intervening file")
        with patch.object(launcher.os, "fsync", side_effect=change):
            with self.assertRaises(OSError):
                self.save()
        self.assertEqual(self.path.read_text(), "intervening file")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_temporary_collision_does_not_delete_other_file(self):
        self.save()
        collision = self.path.parent / ".config-fixed.tmp"
        collision.write_text("do not delete")
        with patch.object(launcher.secrets, "token_hex", return_value="fixed"):
            with self.assertRaises(FileExistsError):
                self.save()
        self.assertEqual(collision.read_text(), "do not delete")

    def test_failed_file_fsync_preserves_old_configuration(self):
        self.save()
        before = self.path.read_bytes()
        with patch.object(launcher.os, "fsync", side_effect=OSError("failed")):
            with self.assertRaises(OSError):
                self.save()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_wrong_owner_is_refused(self):
        with patch.object(launcher.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(OSError):
                self.save()


class FlowRegressionTests(LauncherTestCase):
    def test_saved_copy_launches_without_source_or_catalog(self):
        target = self.root / "Existing.app"
        target.mkdir()
        launcher.save_config(launcher.Config(self.root / "MissingCatalog", target), self.config)
        opened = []
        machine = self.make_launcher(
            self.root / "Absent.app",
            run_cli=lambda argv: (self.calls.append(list(argv)), EXIT_OK)[1],
            choose=lambda kind: self.fail("unexpected picker"),
            verify_source=lambda app: self.fail("unexpected source verification"),
            opener=lambda app: (opened.append(app), (True, ""))[1],
        )
        self.assertEqual(machine.run(), EXIT_OK)
        self.assertEqual([c[0] for c in self.calls], ["verify"])
        self.assertEqual(opened, [target])

    def test_unwritable_parent_stops_before_install_or_save(self):
        machine = self.make_launcher(self.make_app())
        with patch.object(launcher.os, "access", return_value=False):
            self.assertNotEqual(machine.run(catalog=self.make_catalog(), launch=False), EXIT_OK)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.config.exists())

    def test_parent_creation_failure_does_not_save_configuration(self):
        target = self.root / "Applications" / "Out.app"
        machine = self.make_launcher(self.make_app(), default_target=target)
        with patch.object(launcher.Path, "home", return_value=self.root), patch.object(
            launcher.Path, "mkdir", side_effect=PermissionError("denied")
        ):
            self.assertNotEqual(machine.run(catalog=self.root / "catalog", launch=False), EXIT_OK)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.config.exists())

    def test_existing_copy_needs_no_source_catalog_or_config(self):
        target = self.root / "Existing.app"
        target.mkdir()
        machine = self.make_launcher(self.root / "Absent.app", run_cli=lambda argv: (self.calls.append(list(argv)), EXIT_OK)[1], choose=lambda kind: self.fail("unexpected picker"))
        self.assertEqual(machine.run(target=target, launch=False), EXIT_OK)
        self.assertEqual([c[0] for c in self.calls], ["verify"])
        self.assertFalse(self.config.exists())

    def test_install_failure_keeps_partial_target_and_no_config(self):
        app = self.make_app()
        target = self.root / "Partial.app"
        def run(argv):
            if argv[0] == "apply":
                target.mkdir()
            return 1 if argv[0] == "verify" else EXIT_OK
        machine = self.make_launcher(app, run_cli=run)
        self.assertNotEqual(machine.run(catalog=self.make_catalog(), target=target, launch=False), EXIT_OK)
        self.assertTrue(target.exists())
        self.assertFalse(self.config.exists())
        self.assertIn("部分目标保留", self.text())

    def test_custom_missing_parent_is_not_created(self):
        machine = self.make_launcher(self.make_app())
        target = self.root / "missing" / "Out.app"
        self.assertNotEqual(machine.run(catalog=self.make_catalog(), target=target, launch=False), EXIT_OK)
        self.assertFalse(target.parent.exists())
        self.assertFalse(self.config.exists())

    def test_default_applications_parent_is_created(self):
        app = self.make_app()
        target = self.root / "Applications" / "Out.app"
        machine = self.make_launcher(app, default_target=target)
        with patch.object(launcher.Path, "home", return_value=self.root), support.FakeSigning({"com.apple.security.cs.allow-jit": True}):
            self.assertEqual(machine.run(catalog=self.make_catalog(), launch=False), EXIT_OK, self.text())
        self.assertTrue(target.exists())


class PickerRegressionTests(unittest.TestCase):
    def test_only_cancel_returns_none(self):
        with patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "User canceled. (-128)")):
            self.assertIsNone(launcher._osascript("fixed"))
        with patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "denied (-1743)")):
            with self.assertRaises(launcher.LauncherAbort):
                launcher._osascript("fixed")
        with patch.object(launcher.subprocess, "run", side_effect=OSError("missing")):
            with self.assertRaises(launcher.LauncherAbort):
                launcher._osascript("fixed")


class SafetyInvariantTests(unittest.TestCase):
    """The launcher must not do any of the things a one-click installer is
    tempted to do. These check the parsed code, not the prose: the module's
    docstrings discuss these very commands in order to say it does not run them.
    """

    def setUp(self):
        self.path = REPOSITORY / "src" / "claude_zh_patch" / "launcher.py"
        self.source = self.path.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source, filename=str(self.path))
        self.command = COMMAND_FILE.read_text(encoding="utf-8")
        self.constants = {
            node.value
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.called = {
            _dotted(node.func) for node in ast.walk(self.tree) if isinstance(node, ast.Call)
        }

    def test_no_process_is_ever_signalled(self):
        for name in ("os.system", "os.kill", "os.killpg", "os.popen"):
            with self.subTest(name=name):
                self.assertNotIn(name, self.called)
        self.assertFalse(
            [name for name in self.called if name.startswith("signal.")],
            "the launcher reads PIDs but must never signal one",
        )

    def test_no_dangerous_command_is_ever_executed(self):
        """Reading PIDs with pgrep is fine; the banned commands are not."""
        banned = {"sudo", "csrutil", "spctl", "xattr", "kill", "pkill", "killall"}
        for value in self.constants:
            with self.subTest(value=value):
                self.assertNotIn(os.path.basename(value).lower(), banned)

    def test_no_eval_or_dynamic_execution(self):
        for name in ("eval", "exec", "compile", "__import__"):
            with self.subTest(name=name):
                self.assertNotIn(name, self.called)

    def test_no_shell_string_execution(self):
        self.assertNotIn("shell=True", self.source)
        self.assertNotIn("subprocess.getoutput", self.source)

    def test_privilege_escalation_apis_are_absent(self):
        for name in ("os.setuid", "os.seteuid", "AuthorizationCreate"):
            with self.subTest(name=name):
                self.assertNotIn(name, self.called)

    def test_apple_script_prompts_are_two_fixed_strings(self):
        """No user value may ever reach an AppleScript source."""
        choose_folder = next(
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef) and node.name == "choose_folder"
        )
        names = {node.id for node in ast.walk(choose_folder) if isinstance(node, ast.Name)}
        self.assertIn("_CHOOSE_CATALOG", names)
        self.assertIn("_CHOOSE_TARGET_PARENT", names)

        # No interpolation of any kind inside that function.
        self.assertFalse(
            [n for n in ast.walk(choose_folder) if isinstance(n, ast.JoinedStr)],
            "an f-string here would be an injection point",
        )
        self.assertFalse(
            [
                n
                for n in ast.walk(choose_folder)
                if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add)
            ],
            "string concatenation here would be an injection point",
        )

    def test_prompts_are_not_built_with_interpolation_anywhere(self):
        for marker in ('f"POSIX', "f'POSIX", ".format(", "% ("):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.source)

    def test_launcher_does_not_reimplement_the_tool(self):
        """The version gate, signing and ICU validation must stay in the CLI."""
        for forbidden in ("resign_adhoc", "argument_profile", "SUPPORTED_VERSIONS", "codesign"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)

    def test_launcher_calls_the_cli_rather_than_the_internals(self):
        for subcommand in ("check", "apply", "verify"):
            with self.subTest(subcommand=subcommand):
                self.assertIn(subcommand, self.constants)

    def test_command_file_is_executable(self):
        mode = COMMAND_FILE.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, "the .command must be executable")

    def test_command_file_uses_no_eval_or_backtick_substitution(self):
        self.assertNotIn("eval ", self.command)
        self.assertNotIn("`", self.command, "backtick substitution is not used")

    def test_command_file_does_not_escalate_or_disable_protections(self):
        for forbidden in ("sudo", "csrutil", "spctl", "xattr -d", "kill"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.command)

    def test_command_file_quotes_its_own_location(self):
        self.assertIn('"${BASH_SOURCE[0]}"', self.command)
        self.assertIn('"$(dirname -- "$SOURCE")"', self.command)

    def test_command_file_keeps_the_window_open_on_failure(self):
        self.assertIn('if [ "$STATUS" -ne 0 ]', self.command)
        self.assertIn("read -r _", self.command)

    def test_command_file_explains_a_missing_python(self):
        self.assertIn("xcode-select --install", self.command)
        self.assertIn("没有找到可用的 Python", self.command)

    def test_command_file_delegates_to_the_launcher_module(self):
        self.assertIn("claude_zh_patch.launcher", self.command)


def _dotted(node: ast.AST) -> str:
    """Render a call target such as ``subprocess.run`` as a dotted name."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


class CommandScriptBehaviourTests(unittest.TestCase):
    """Run the .command as the Finder would, through /bin/bash."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()

    def _run(self, argv, *, env=None):
        return subprocess.run(
            ["/bin/bash", str(COMMAND_FILE), *argv],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env=env,
            cwd=str(self.root),
        )

    def test_help_is_reachable(self):
        result = self._run(["--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--catalog-dir", result.stdout)

    def test_an_unusable_python_override_falls_back_to_a_working_one(self):
        """A stale override must not brick the script.

        ``/usr/bin/python3`` is only a stub when the command line tools are
        absent, so the script probes several candidates rather than trusting the
        first one it is handed.
        """
        env = dict(os.environ)
        env["CLAUDE_ZH_PATCH_PYTHON"] = str(self.root / "not-python")
        result = self._run(["--help"], env=env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_failure_does_not_exit_zero(self):
        """A refusal must reach the caller as a non-zero status."""
        result = self._run(["apply", "--catalog-dir", str(self.root / "nope")])
        self.assertNotEqual(result.returncode, 0, "a failure must not look like success")
        self.assertIn("error", (result.stdout + result.stderr).lower())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
