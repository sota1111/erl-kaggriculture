#!/usr/bin/env bash
# Build a Kaggriculture submission archive from an agent directory.
#
#   tools/build_submission.sh results/r1/<agent-id>          -> results/r1/<agent-id>/submission.tar.gz
#   tools/build_submission.sh baseline/moon198               -> baseline/moon198/submission.tar.gz
#
# The directory must contain main.py exporting agent(obs). Any extra files in the
# directory (helper modules, model weights) are bundled alongside it, with main.py
# at the archive root, which is what the arena expects.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
dir="$(cd "${1:?usage: build_submission.sh <agent-dir>}" && pwd)"
test -f "$dir/main.py" || { echo "no main.py in $dir" >&2; exit 1; }

python3 "$repo/tools/validate_submission.py" "$dir/main.py"

out="$dir/submission.tar.gz"
tar -C "$dir" -czf "$out" \
  --exclude='submission.tar.gz' --exclude='__pycache__' --exclude='*.pyc' \
  $(cd "$dir" && ls -A | grep -v -E '^(submission\.tar\.gz|__pycache__)$')
gzip -t "$out"
tar -tzf "$out" | grep -qx 'main.py' || { echo "main.py not at archive root" >&2; exit 1; }

echo "archive : $out"
echo "sha256  : $(sha256sum "$out" | cut -d' ' -f1)"
echo "main.py : $(sha256sum "$dir/main.py" | cut -d' ' -f1)"
echo "contents:"; tar -tzf "$out" | sed 's/^/  /'
