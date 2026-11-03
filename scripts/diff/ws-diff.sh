#!/bin/bash
# Step 6: event stream of the websocket server on an old and a new node, compared.
# Usage: [WS_FIX=run-app-loop] scripts/diff/ws-diff.sh <new arch: arm64|amd64>
set -euo pipefail
arch=$1
root=$(cd "$(dirname "$0")/../.." && pwd)
out=$root/test-results/diff
suffix=${WS_FIX:+-$WS_FIX}
for side in old:amd64 "new:$arch"; do
  env=${side%%:*} a=${side##*:}
  "$root/scripts/diff/node.sh" "$env" "$a" up
  sleep 5
  docker run --rm --network "bdb-node-$env-$a-net" -v "$root:/src:ro" -v "$out:/out" "bdb-new-env:arm64" \
    python -I /src/scripts/diff/ws_client.py /out/corpus-old-amd64.json "/out/ws-$env-$a$suffix.json"
  "$root/scripts/diff/node.sh" "$env" "$a" logs > "$out/ws-$env-$a$suffix-node.log" 2>&1
  "$root/scripts/diff/node.sh" "$env" "$a" down
done
python3 "$root/scripts/diff/compare.py" "$out/ws-old-amd64$suffix.json" "$out/ws-new-$arch$suffix.json" \
  > "$out/compare-ws-old-amd64-new-$arch$suffix.txt" || true
tail -1 "$out/compare-ws-old-amd64-new-$arch$suffix.txt"
