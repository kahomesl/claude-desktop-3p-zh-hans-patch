"""Double-clickable installer and launcher for the Simplified Chinese copy.

This is the entry point behind ``启动Claude中文版.command``. It exists so that a
non-technical user can double-click one file and get a working Chinese interface,
instead of typing a sequence of terminal commands.

Design rules this module follows, and why:

* **It does not weaken the tool.** The launcher calls the same ``check``,
  ``apply`` and ``verify`` commands as the command line. The version allowlist,
  the ad-hoc signing and the ICU validation are untouched. A build the CLI would
  refuse is refused here too, with an explanation rather than a silent exit.
* **It never overwrites.** An existing target bundle is verified, never replaced.
  ``apply`` refuses an existing path by design, and the launcher treats that as a
  normal outcome, not an error to work around.
* **It never escalates.** No ``sudo``, no disabling SIP, no Gatekeeper changes,
  no killing processes. Everything runs as the invoking user, and the default
  target is under the user's home directory so that no privilege is needed.
* **Failures are visible.** Every step prints what it is doing in Chinese, and
  every failure prints what went wrong and what to do next. Nothing returns 0
  while having done nothing.
* **No shell string building.** Subprocess calls take argument lists; no user
  value is ever interpolated into a shell command or an AppleScript source.

The configuration file records only the two paths the user chose. It holds no
translation data, no credentials and nothing derived from the application.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from . import bundle, cli
from .catalog import CatalogError, load_catalog
from .compat import DEFAULT_SOURCE_APP
from .errors import (
    EXIT_CATALOG,
    EXIT_INCOMPATIBLE_BUNDLE,
    EXIT_OK,
    EXIT_UNSUPPORTED_VERSION,
    PatchError,
)

SCHEMA_VERSION = 1

CONFIG_DIR = Path.home() / ".config" / "claude-zh-patch"
CONFIG_PATH = CONFIG_DIR / "config.json"
CONFIG_FILE_MODE = 0o600
CONFIG_DIR_MODE = 0o700

#: The official bundle. Both the source of a patch and the one path that must
#: never be written to.
OFFICIAL_APP = Path(DEFAULT_SOURCE_APP)

#: Where the localised copy goes by default. Under the home directory, so that
#: installing needs no administrator rights.
DEFAULT_TARGET = Path.home() / "Applications" / "Claude-3P-ZH.app"

APP_NAME = "Claude-3P-ZH.app"

#: Directories that are never a legitimate destination. ``/private`` is
#: deliberately not listed: ``/tmp`` is a symlink into it, and refusing scratch
#: space would reject perfectly harmless choices for no benefit.
SYSTEM_ROOTS = ("/System", "/usr", "/bin", "/sbin", "/cores", "/Library")

# Fixed prompts. Interpolating anything into an AppleScript source is how shell
# and script injection gets in, so these are literals and stay literals.
_CHOOSE_CATALOG = (
    "POSIX path of (choose folder with prompt "
    '"请选择你准备好的语言资源目录（catalog）")'
)
_CHOOSE_TARGET_PARENT = (
    "POSIX path of (choose folder with prompt "
    '"请选择放置“Claude-3P-ZH.app”的位置（例如“应用程序”或你自己的文件夹）")'
)

OSASCRIPT = "/usr/bin/osascript"
OPEN = "/usr/bin/open"
PGREP = "/usr/bin/pgrep"


class LauncherAbort(Exception):
    """A user-facing stop. The message is already written for the user to read."""


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """The two paths the user chose, and nothing else."""

    catalog: Path
    target: Path

    def as_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "catalogPath": str(self.catalog),
            "targetApp": str(self.target),
        }


def load_config(path: Path | None = None) -> Config | None:
    """Read the saved configuration, or ``None`` when there is not a usable one."""
    path = Path(path) if path is not None else CONFIG_PATH
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schemaVersion") != SCHEMA_VERSION:
        return None
    catalog = data.get("catalogPath")
    target = data.get("targetApp")
    if not isinstance(catalog, str) or not isinstance(target, str):
        return None
    if not catalog or not target:
        return None
    return Config(catalog=Path(catalog), target=Path(target))


def save_config(config: Config, path: Path | None = None) -> Path:
    """Write the configuration with mode 600, creating its directory if needed.

    The file is created with the restrictive mode rather than chmod-ed
    afterwards, so it is never briefly readable by anyone else.
    """
    path = Path(path) if path is not None else CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, CONFIG_DIR_MODE)
    except OSError:
        pass

    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, CONFIG_FILE_MODE)
    try:
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
    except Exception:
        os.close(descriptor)
        raise
    with handle:
        json.dump(config.as_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(path, CONFIG_FILE_MODE)
    return path


# ---------------------------------------------------------------------------
# console
# ---------------------------------------------------------------------------


class Console:
    """All user interaction, so tests can drive the launcher without a terminal."""

    def __init__(
        self,
        out=None,
        err=None,
        read: Callable[[str], str] | None = None,
    ) -> None:
        self.out = out if out is not None else sys.stdout
        self.err = err if err is not None else sys.stderr
        self._read = read

    def say(self, text: str = "") -> None:
        # Flushed so that progress and errors stay in order when the output is
        # piped or captured rather than shown in a terminal.
        print(text, file=self.out, flush=True)

    def warn(self, text: str = "") -> None:
        print(text, file=self.err, flush=True)

    def rule(self) -> None:
        self.say("─" * 60)

    def ask(self, prompt: str) -> str:
        self.say(prompt)
        if self._read is not None:
            return self._read(prompt)
        try:
            return input("> ")
        except EOFError:
            return ""

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        answer = self.ask(prompt).strip().lower()
        if not answer:
            return default
        return answer in ("y", "yes", "是", "好", "确定")


# ---------------------------------------------------------------------------
# environment probes
# ---------------------------------------------------------------------------


def _osascript(script: str) -> str | None:
    """Run a fixed AppleScript. Returns stdout, or ``None`` if the user cancelled."""
    result = subprocess.run(
        [OSASCRIPT, "-e", script], capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def choose_folder(kind: str) -> Path | None:
    """Open the native folder chooser. Returns ``None`` when cancelled.

    ``kind`` is ``"catalog"`` or ``"target"`` and selects one of two fixed
    scripts; no caller-supplied text reaches AppleScript.
    """
    script = _CHOOSE_CATALOG if kind == "catalog" else _CHOOSE_TARGET_PARENT
    selected = _osascript(script)
    if not selected:
        return None
    # ``choose folder`` yields a path with a trailing slash; "/" is the one case
    # where stripping it would leave nothing.
    trimmed = selected.strip()
    if trimmed != "/":
        trimmed = trimmed.rstrip("/")
    return Path(trimmed)


def running_claude_pids() -> list[int]:
    """PIDs of running Claude processes. Read-only: nothing is signalled."""
    try:
        result = subprocess.run(
            [PGREP, "-x", "Claude"], capture_output=True, text=True
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [int(line) for line in result.stdout.split() if line.isdigit()]


def open_app(target: Path) -> tuple[bool, str]:
    """Ask the Finder to open ``target``. Returns ``(ok, detail)``."""
    result = subprocess.run(
        [OPEN, "-n", "-a", str(target)], capture_output=True, text=True
    )
    detail = (result.stderr or result.stdout).strip()
    return result.returncode == 0, detail


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def validate_target(target: Path, *, official: Path = OFFICIAL_APP) -> None:
    """Refuse a destination that could damage something.

    The target may not be the official application, may not live inside it, may
    not sit under a system directory, and must look like an application bundle.
    Whether it already exists is handled by the caller, which verifies instead of
    writing.
    """
    target = Path(target).expanduser()

    if target.suffix != ".app":
        raise LauncherAbort(
            f"目标必须是 .app 结尾的应用包，当前是：{target}"
        )

    resolved = target.resolve()
    official_resolved = Path(official).expanduser().resolve()

    if resolved == official_resolved:
        raise LauncherAbort(
            f"拒绝把官方应用本身作为目标：{resolved}\n"
            "官方 Claude.app 永远不会被修改，请换一个位置。"
        )
    if official_resolved in resolved.parents:
        raise LauncherAbort(
            f"目标位于官方应用内部，这是不允许的：{resolved}"
        )
    if resolved == Path("/"):
        raise LauncherAbort("拒绝把根目录作为目标。")

    for root in SYSTEM_ROOTS:
        root_path = Path(root)
        if resolved == root_path or root_path in resolved.parents:
            raise LauncherAbort(
                f"拒绝写入系统目录：{root}\n请改选你自己的文件夹，例如 ~/Applications。"
            )

    parent = resolved.parent
    if parent.exists() and not os.access(parent, os.W_OK):
        raise LauncherAbort(
            f"没有写入权限：{parent}\n请换一个你有写权限的位置。"
        )


# ---------------------------------------------------------------------------
# launcher
# ---------------------------------------------------------------------------


class Launcher:
    """The double-click experience, with every side effect injectable."""

    def __init__(
        self,
        console: Console | None = None,
        *,
        config_path: Path | None = None,
        source_app: Path | None = None,
        default_target: Path | None = None,
        choose: Callable[[str], Path | None] | None = None,
        run_cli: Callable[[Sequence[str]], int] | None = None,
        pids: Callable[[], list[int]] | None = None,
        opener: Callable[[Path], tuple[bool, str]] | None = None,
        verify_source: Callable[[Path], tuple[bool, str]] | None = None,
    ) -> None:
        self.console = console if console is not None else Console()
        self.config_path = Path(config_path) if config_path else CONFIG_PATH
        self.source_app = Path(source_app) if source_app else OFFICIAL_APP
        self.default_target = (
            Path(default_target) if default_target else DEFAULT_TARGET
        )
        self.choose = choose if choose is not None else choose_folder
        self.run_cli = run_cli if run_cli is not None else _run_cli
        self.pids = pids if pids is not None else running_claude_pids
        self.opener = opener if opener is not None else open_app
        self.verify_source = (
            verify_source if verify_source is not None else bundle.verify_signature
        )

    # -- pieces ------------------------------------------------------------

    def banner(self) -> None:
        self.console.rule()
        self.console.say("Claude Desktop 简体中文版 — 一键安装 / 启动")
        self.console.say("")
        self.console.say("这个工具会在你自己的目录里生成一个独立的中文副本，")
        self.console.say("不会修改官方 Claude.app，也不会改动你的任何数据。")
        self.console.rule()
        self.console.say("")

    def step(self, number: int, total: int, text: str) -> None:
        self.console.say(f"[{number}/{total}] {text}")

    def source_version(self) -> str:
        try:
            return bundle.read_version(self.source_app) or "未知"
        except PatchError:
            return "未知"

    def resolve_catalog(self, saved: Path | None) -> Path:
        """Return a catalog directory that loads, prompting until one does."""
        candidate = saved
        first = True
        while True:
            if candidate is None:
                self.console.say("")
                self.console.say(
                    "本项目不包含任何中文翻译内容，需要你自己指定语言资源目录。"
                )
                self.console.say("如果你还没有，请先按 docs/CATALOG-FORMAT.md 准备，")
                self.console.say("或运行 ./zh-patch keys 生成待翻译的 key 清单。")
                self.console.say("")
                self.console.say("即将打开文件选择窗口，请选择该目录。")
                selected = self.choose("catalog")
                if selected is None:
                    raise LauncherAbort("已取消选择语言资源目录，未做任何改动。")
                candidate = selected

            try:
                load_catalog(candidate)
            except CatalogError as exc:
                self.console.warn("")
                self.console.warn(f"✗ 这个目录不能用作语言资源：{exc.message}")
                if exc.detail:
                    for line in exc.detail.splitlines():
                        self.console.warn(f"  {line}")
                self.console.warn("")
                if not first:
                    self.console.warn("请重新选择，或按 Control-C 退出。")
                candidate = None
                first = False
                continue
            return candidate

    def resolve_target(self, saved: Path | None, *, explicit: Path | None) -> Path:
        """Return the destination, offering a choice when the default is unclear."""
        if explicit is not None:
            return Path(explicit).expanduser()
        if saved is not None:
            return saved.expanduser()

        self.console.say("")
        self.console.say(f"中文版将安装到：{self.default_target}")
        if self.console.confirm("使用这个位置吗？（回车 = 是，输入 n 另选）", default=True):
            return self.default_target

        selected = self.choose("target")
        if selected is None:
            raise LauncherAbort("已取消选择安装位置，未做任何改动。")
        return Path(selected) / APP_NAME

    def explain_exit(self, code: int) -> None:
        """Turn an exit code into something a user can act on."""
        self.console.warn("")
        if code == EXIT_UNSUPPORTED_VERSION:
            self.console.warn(
                f"✗ Claude Desktop 版本不受支持（当前：{self.source_version()}）。"
            )
            self.console.warn("")
            self.console.warn("本工具只支持已验证过的版本，而且没有强制绕过的参数——")
            self.console.warn("对结构未经验证的版本打补丁，结果通常是一个坏掉的应用。")
            self.console.warn("")
            self.console.warn("如果你的应用已经自动升级，请保留一份受支持版本的副本，")
            self.console.warn("再用它作为源：见 docs/INSTALL.zh-Hans.md 的“从备份安装”。")
        elif code == EXIT_CATALOG:
            self.console.warn("✗ 语言资源未通过校验，上面已列出具体原因。")
            self.console.warn("请修正后重试；也可以运行 ./zh-patch lint 查看完整报告。")
        elif code == EXIT_INCOMPATIBLE_BUNDLE:
            self.console.warn("✗ 应用结构或签名校验未通过。")
            self.console.warn(
                "常见原因：该应用已被修改过、签名损坏，或不是受支持的构建。"
            )
            self.console.warn("请先用一份干净的官方副本再试。")
        else:
            self.console.warn(f"✗ 操作失败（退出码 {code}），上面是详细信息。")
        self.console.warn("")

    def preflight_source(self) -> None:
        """Fail early, and specifically, when the source application is unusable."""
        if not self.source_app.is_dir():
            raise LauncherAbort(
                f"没有找到官方应用：{self.source_app}\n"
                "请先安装 Claude Desktop，或把它放回默认位置。"
            )
        ok, detail = self.verify_source(self.source_app)
        if not ok:
            self.console.warn("")
            self.console.warn(f"✗ 官方应用的签名校验未通过：{self.source_app}")
            if detail:
                for line in detail.strip().splitlines()[-4:]:
                    self.console.warn(f"  {line}")
            self.console.warn("")
            raise LauncherAbort(
                "这个副本已损坏或被修改过，无法作为补丁来源。\n"
                "请重新安装一份干净的官方应用。"
            )

    # -- phases ------------------------------------------------------------

    def install(self, catalog: Path, target: Path) -> int:
        """check → apply → verify, stopping at the first failure."""
        self.console.say("")
        self.step(2, 5, "检查应用版本与语言资源（不会写入任何文件）…")
        code = self.run_cli(
            ["check", "--app", str(self.source_app), "--catalog-dir", str(catalog)]
        )
        if code != EXIT_OK:
            self.explain_exit(code)
            return code

        self.step(3, 5, "生成中文副本并重新签名（需要一点时间）…")
        code = self.run_cli(
            [
                "apply",
                "--app",
                str(self.source_app),
                "--target",
                str(target),
                "--catalog-dir",
                str(catalog),
            ]
        )
        if code != EXIT_OK:
            self.explain_exit(code)
            return code

        self.step(4, 5, "校验生成结果…")
        code = self.run_cli(["verify", "--target", str(target)])
        if code != EXIT_OK:
            self.explain_exit(code)
            return code

        return EXIT_OK

    def check_existing(self, target: Path) -> tuple[bool, int]:
        """Verify an existing copy instead of writing over it."""
        self.console.say("")
        self.step(2, 5, f"目标已存在，先校验而不是覆盖：{target}")
        code = self.run_cli(["verify", "--target", str(target)])
        return code == EXIT_OK, code

    def confirm_launch(self) -> bool:
        """Warn about other instances, then ask. Never kills anything."""
        pids = self.pids()
        if pids:
            self.console.say("")
            self.console.warn(
                f"注意：检测到 {len(pids)} 个正在运行的 Claude 进程。"
            )
            self.console.warn(
                "中文副本与官方版共用同一份用户数据目录，同时运行可能造成写入冲突。"
            )
            self.console.warn("建议先手动退出它们，本工具不会替你结束进程。")
        self.console.say("")
        return self.console.confirm("现在启动中文版吗？", default=True)

    def launch(self, target: Path) -> int:
        if not self.confirm_launch():
            self.console.say("")
            self.console.say("好的，没有启动。之后可以随时双击本文件来打开中文版。")
            return EXIT_OK

        self.step(5, 5, "启动中文版…")
        ok, detail = self.opener(target)
        if not ok:
            self.console.warn("")
            self.console.warn(f"✗ 启动失败：{target}")
            if detail:
                for line in detail.splitlines()[:5]:
                    self.console.warn(f"  {line}")
            self.console.warn("")
            self.console.warn(
                "如果提示被系统阻止，通常是因为文件带有“下载隔离”标记——"
            )
            self.console.warn(
                "由本工具在本机生成的副本不会被隔离。详见 docs/TROUBLESHOOTING.zh-Hans.md。"
            )
            return 1
        return EXIT_OK

    # -- entry -------------------------------------------------------------

    def run(
        self,
        *,
        catalog: Path | None = None,
        target: Path | None = None,
        launch: bool = True,
    ) -> int:
        self.banner()

        saved = load_config(self.config_path)

        self.step(1, 5, "读取配置…")
        try:
            self.preflight_source()
            chosen_catalog = (
                Path(catalog).expanduser()
                if catalog is not None
                else self.resolve_catalog(saved.catalog if saved else None)
            )
            chosen_target = self.resolve_target(
                saved.target if saved else None, explicit=target
            )
            validate_target(chosen_target, official=self.source_app)
        except LauncherAbort as exc:
            self.console.warn("")
            self.console.warn(str(exc))
            self.console.warn("")
            return 1

        try:
            save_config(
                Config(catalog=chosen_catalog, target=chosen_target), self.config_path
            )
        except OSError as exc:
            self.console.warn(f"提示：无法保存配置（{exc}），下次仍需重新选择。")

        if chosen_target.exists():
            verified, code = self.check_existing(chosen_target)
            if not verified:
                self.console.warn("")
                self.console.warn("✗ 已存在的副本未通过校验，它可能已损坏或不属于本工具。")
                self.console.warn("本工具不会覆盖它。你可以：")
                self.console.warn("  · 手动重命名或删除它，然后重新双击本文件；")
                self.console.warn(
                    f"  · 或运行 ./zh-patch rollback --target '{chosen_target}' 把它移到废纸篓。"
                )
                self.console.warn("")
                return code
            self.console.say("✓ 已存在的副本校验通过。")
        else:
            code = self.install(chosen_catalog, chosen_target)
            if code != EXIT_OK:
                return code
            self.console.say("")
            self.console.say("✓ 安装完成。")
            self.console.say(
                "提示：副本使用 ad-hoc 签名，与官方版的钥匙串条目不通用，"
            )
            self.console.say("可能需要重新登录；部分依赖签名的原生功能也可能不同。")

        if not launch:
            self.console.say("")
            self.console.say(f"中文版位于：{chosen_target}")
            return EXIT_OK

        return self.launch(chosen_target)


def _run_cli(argv: Sequence[str]) -> int:
    try:
        return cli.main(list(argv))
    except SystemExit as exc:  # argparse usage errors
        code = exc.code
        return int(code) if isinstance(code, int) else 1


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="claude-zh-patch-launcher",
        description=(
            "双击启动器背后的逻辑。通常由 启动Claude中文版.command 调用，"
            "也可以直接运行以便脚本化。"
        ),
    )
    parser.add_argument(
        "--catalog-dir",
        help="语言资源目录；省略时读取配置，配置也没有则弹出选择窗口",
    )
    parser.add_argument("--target", help=f"中文副本的位置（默认 {DEFAULT_TARGET}）")
    parser.add_argument(
        "--no-launch", action="store_true", help="完成后不启动，只安装"
    )
    parser.add_argument(
        "--config", help="配置文件位置（默认 ~/.config/claude-zh-patch/config.json）"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    launcher = Launcher(config_path=Path(args.config) if args.config else None)
    return launcher.run(
        catalog=Path(args.catalog_dir) if args.catalog_dir else None,
        target=Path(args.target) if args.target else None,
        launch=not args.no_launch,
    )


if __name__ == "__main__":  # pragma: no cover - exercised through the .command
    sys.exit(main())


__all__ = [
    "Console",
    "Config",
    "Launcher",
    "LauncherAbort",
    "choose_folder",
    "load_config",
    "main",
    "open_app",
    "running_claude_pids",
    "save_config",
    "validate_target",
]
