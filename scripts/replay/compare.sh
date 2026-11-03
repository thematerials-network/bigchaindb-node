#!/bin/bash
# Compares the two replay sides after both finished: Tendermint replay outcome and per-block executed counts,
# BigchainDB rejections (WARNING lines) in order, the MongoDB dumps, and both sides against the JSONL/CSV.
# Usage: scripts/replay/compare.sh <new arch>    (old side is always amd64)
# Expects test-results/replay/{old-amd64,new-<arch>}/ from collect.sh.
set -euo pipefail
arch=$1
out=$(cd "$(dirname "$0")/../.." && pwd)/test-results/replay
old=$out/old-amd64 new=$out/new-$arch report=$out/compare-old-amd64-new-$arch.txt
{
  for side in "$old" "$new"; do
    echo "== $(basename "$side")"
    grep -c 'Applying block' "$side/tendermint.log" | sed 's/^/blocks applied by handshake: /'
    grep -E 'Completed ABCI Handshake|panic|AppHash|error' "$side/tendermint.log" | head -5 | cut -c1-300 || true
  done
  echo "== executed-block counts (height validTxs invalidTxs), old vs new"
  diff <(cut -f1-3 "$old/executed.tsv") <(cut -f1-3 "$new/executed.tsv") && echo identical
  echo "== BigchainDB rejection warnings, old vs new"
  diff "$old/rejections.txt" "$new/rejections.txt" && echo "identical ($(wc -l < "$old/rejections.txt") lines)"
  echo "== MongoDB collections"
  for file in "$old"/*.jsonl; do
    name=$(basename "$file")
    if cmp -s "$file" "$new/$name"; then echo "$name identical ($(wc -l < "$file") documents)"
    else echo "$name DIFFERS: $(diff "$file" "$new/$name" | grep -c '^[<>]') lines"; fi
  done
  python3 -c '
import json, sys
old, new = (json.load(open(path)) for path in sys.argv[1:3])
for name in sorted(set(old) | set(new)):
    same = old.get(name, {}).get("indexes") == new.get(name, {}).get("indexes")
    print("indexes", name, "identical" if same else "DIFFER")
' "$old/summary.json" "$new/summary.json"
  echo "== blocks.tsv (height, app hash, accepted ids)"
  cmp "$old/blocks.tsv" "$new/blocks.tsv" && echo "identical ($(wc -l < "$old/blocks.tsv") blocks)"
  echo "== against JSONL/CSV"
  cat "$old/check-inputs.txt" "$new/check-inputs.txt"
} > "$report" 2>&1 || true
cat "$report"
