#!/bin/bash
# Step 5: runs http_diff.py against a fresh old node and a fresh new node, then compares.
# Usage: [REQPARSE=args-only] scripts/diff/http-diff.sh <new arch: arm64|amd64> [--crash]
set -euo pipefail
arch=$1
shift
root=$(cd "$(dirname "$0")/../.." && pwd)
out=$root/test-results/diff
suffix=${1:+-crash}${REQPARSE:+-$REQPARSE}
declare_ports() { case $1-$2 in old-amd64) echo "19984 16657" ;; new-arm64) echo "29984 26657" ;; new-amd64) echo "39984 36657" ;; esac; }
for side in old:amd64 "new:$arch"; do
  env=${side%%:*} a=${side##*:}
  read -r api rpc <<< "$(declare_ports "$env" "$a")"
  "$root/scripts/diff/node.sh" "$env" "$a" up
  python3 "$root/scripts/diff/http_diff.py" "$out/corpus-old-amd64.json" "$api" "$rpc" "$out/http-$env-$a$suffix.json" "$@"
  "$root/scripts/diff/node.sh" "$env" "$a" logs > "$out/http-$env-$a$suffix-node.log" 2>&1
  "$root/scripts/diff/node.sh" "$env" "$a" down
done
python3 "$root/scripts/diff/compare.py" "$out/http-old-amd64$suffix.json" "$out/http-new-$arch$suffix.json" \
  > "$out/compare-http-old-amd64-new-$arch$suffix.txt" || true
tail -1 "$out/compare-http-old-amd64-new-$arch$suffix.txt"
