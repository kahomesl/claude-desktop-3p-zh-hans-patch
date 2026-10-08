#!/usr/bin/env bash
# Static scan for secrets, personal data and third-party material.
#
#   ./scripts/security-scan.sh [path]
#
# Exits non-zero if anything was found. Findings never echo the matched value.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
target="${1:-$here}"

"$here/zh-patch" scan "$target"
