#!/bin/bash
#
# 双击我 —— 安装或启动 Claude Desktop 简体中文版
# Double-click me to install or launch the Simplified Chinese copy.
#
# 这是一个很薄的外壳。真正的逻辑全部在 Python 里
# （src/claude_zh_patch/launcher.py），这样它才能被自动化测试覆盖。
# 本文件只做三件事：找到自己的目录、确认有可用的 Python、把控制权交出去。
#
# 它不会：索取管理员密码、关闭 SIP 或 Gatekeeper、结束任何进程、
#         修改官方 Claude.app，或把任何用户输入拼进 shell 命令。

set -u

# --- 找到本脚本自己的真实位置（符号链接也处理）---------------------------
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P -- "$(dirname -- "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink -- "$SOURCE")"
  case "$SOURCE" in
    /*) ;;
    *) SOURCE="$DIR/$SOURCE" ;;
  esac
done
ROOT="$(cd -P -- "$(dirname -- "$SOURCE")" >/dev/null 2>&1 && pwd)"

if [ ! -d "$ROOT/src/claude_zh_patch" ]; then
  printf '%s\n' "✗ 找不到 src/claude_zh_patch，请确认本文件仍在本项目目录内。" >&2
  printf '%s\n' "  当前位置：$ROOT" >&2
  exit 1
fi

# --- 找一个可用的 Python 3 ------------------------------------------------
# macOS 从 12.3 起不再自带 Python；/usr/bin/python3 可能只是触发
# “命令行工具”安装的桩，运行它会返回非零。这里逐个探测，全部失败才报错。
find_python() {
  local candidates=() candidate from_path
  if [ -n "${CLAUDE_ZH_PATCH_PYTHON:-}" ]; then
    candidates+=("$CLAUDE_ZH_PATCH_PYTHON")
  fi
  candidates+=("/usr/bin/python3" "/opt/homebrew/bin/python3" "/usr/local/bin/python3")
  from_path="$(command -v python3 2>/dev/null || true)"
  if [ -n "$from_path" ]; then
    candidates+=("$from_path")
  fi
  for candidate in "${candidates[@]}"; do
    if [ -x "$candidate" ] && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON="$(find_python)" || PYTHON=""
if [ -z "$PYTHON" ]; then
  printf '\n%s\n' "✗ 没有找到可用的 Python 3.9 或更新版本。"
  printf '\n%s\n' "本工具是 Python 程序，需要 Python 才能运行。macOS 从 12.3 起不再自带它，"
  printf '%s\n' "因此你需要先安装“命令行工具”（免费，来自 Apple）："
  printf '\n%s\n' "    xcode-select --install"
  printf '\n%s\n' "在弹出的窗口中点“安装”，等它完成后再双击本文件。"
  printf '\n%s\n' "或者安装 Homebrew 版 Python：https://brew.sh"
  printf '\n'
  exit 1
fi

# --- 交给 Python ----------------------------------------------------------
# 用 -c 而不是 -m，并且把 src 插到 sys.path 最前面，
# 这样即使环境里存在别的同名包也不会被误用。
"$PYTHON" -c '
import runpy, sys
sys.path.insert(0, sys.argv.pop(1))
runpy.run_module("claude_zh_patch.launcher", run_name="__main__")
' "$ROOT/src" "$@"
STATUS=$?

# --- 失败时留住窗口 -------------------------------------------------------
# Terminal 的默认设置会在“干净退出”时自动关窗。失败时我们让脚本在此等待，
# 用户才看得见错误信息——绝不静默失败。
if [ "$STATUS" -ne 0 ] && [ -t 0 ]; then
  printf '\n%s\n' "────────────────────────────────────────────────────────────"
  printf '%s\n' "出现错误，窗口保持打开，方便你查看上面的信息。"
  printf '%s' "按回车键关闭此窗口… "
  read -r _ || true
fi

exit "$STATUS"
