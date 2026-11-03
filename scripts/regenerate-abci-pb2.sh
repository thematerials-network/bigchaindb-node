#!/bin/bash
# Regenerates bigchaindb-abci's _pb2 modules from the descriptors embedded in the original 1.0.5 modules.
# Usage: scripts/regenerate-abci-pb2.sh <dir containing the original 1.0.5 abci_pb> [python]
set -euo pipefail

original=$1
python=${2:-python3}
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

"$python" -I "$root/scripts/extract_abci_descriptors.py" "$original" "$work/abci.pb" > "$work/files.txt"
include=$(dirname "$(dirname "$(command -v protoc)")")/include
mkdir "$work/out"
# shellcheck disable=SC2046
protoc --descriptor_set_in="$work/abci.pb" -I "$include" --python_out="$work/out" $(cat "$work/files.txt")

target=$root/bigchaindb-abci
while read -r proto; do
  # protoc maps the dot in github.com to a package level, as the original layout does.
  module=$(echo "${proto%.proto}_pb2.py" | sed 's|github\.com|github/com|')
  destination=$target/$module
  { sed -n 1p "$work/out/$module"; echo "# Modified by thematerials-network contributors, 2026; see NOTICE at the repository root."; sed 1d "$work/out/$module"; } > "$destination"
  echo "$destination"
done < "$work/files.txt"
