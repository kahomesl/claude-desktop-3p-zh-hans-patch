#!/usr/bin/env bash
# Run the whole test suite, then the repository's own scanner.
#
#   ./scripts/check.sh
#
# Both must pass before a release is tagged.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$here"

echo "== unit tests =="
python3 -m unittest discover -s tests -t . "$@"

echo
echo "== security scan =="
./zh-patch scan .

echo
echo "both clean"
