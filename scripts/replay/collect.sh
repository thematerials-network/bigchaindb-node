#!/bin/bash
# After a side's replay finished: saves logs, extracts per-block counts and rejection warnings, dumps MongoDB and
# checks the side against the JSONL/CSV. Dump and check run in containers on the side's internal network.
# Usage: scripts/replay/collect.sh <old|new> <arm64|amd64>
set -euo pipefail
env=$1 arch=$2
root=$(cd "$(dirname "$0")/../.." && pwd)
prefix=bdb-replay-$env-$arch network=$prefix-net
out=$root/test-results/replay/$env-$arch
mkdir -p "$out"
docker logs "$prefix-tendermint" > "$out/tendermint.log" 2>&1
docker logs "$prefix-bigchaindb" > "$out/bigchaindb.log" 2>&1
# Tendermint state/execution.go execBlockOnProxyApp: "Executed block" height=… validTxs=… invalidTxs=…
grep 'Executed block' "$out/tendermint.log" | sed -E 's/.*height=([0-9]+) validTxs=([0-9]+) invalidTxs=([0-9]+).*/\1\t\2\t\3/' > "$out/executed.tsv"
# lib.py validate_transaction / is_valid_transaction log every rejection as WARNING with the exception class
grep -E 'WARNING|ERROR|CRITICAL|Traceback' "$out/bigchaindb.log" | sed -E 's/^\[[^]]*\] //; s/ \([^()]* - pid: [0-9]+\)$//' > "$out/rejections.txt" || true
docker run --rm --network "$network" -v "$root:/src:ro" -v "$out:/out" bdb-new-env:arm64 \
  python -I /src/scripts/replay/dump.py mongodb /out
inputs=/src/test-results/replay/inputs
"$root/scripts/diff/run-in-env.sh" "$env" "$arch" --network "$network" -e BIGCHAINDB_DATABASE_HOST=mongodb -v "$out:/side" -- \
  python -I -W ignore /src/scripts/replay/check_inputs.py "$inputs/rebuilt-transactions.jsonl" \
  "$inputs/step7-block-membership-2026-10-22.csv" /side/blocks.tsv /side/check-inputs.json | tail -1 \
  | sed "s/^/$env-$arch: /" > "$out/check-inputs.txt"
cat "$out/check-inputs.txt"
