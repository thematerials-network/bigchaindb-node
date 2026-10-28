#!/bin/bash
# Copies the old-chain replay inputs (read-only originals in ~/s1seven/old-chain-work) into test-results/replay/inputs,
# verifies every copy against the recorded SHA-256, and makes the copies read-only.
# Inputs: rebuilt/rebuilt-transactions.jsonl (+ .sha256), step7-block-membership-2026-10-22.csv,
#         extract/tendermint/config/genesis.json and extract/tendermint/data/{blockstore,state,evidence,tx_index}.db
#         (checked against extract/SHA256SUMS). Never copied: config.toml, addrbook.json (peers of the real network).
set -euo pipefail
src=${OLD_CHAIN_WORK:-$HOME/s1seven/old-chain-work}
root=$(cd "$(dirname "$0")/../.." && pwd)
dst=$root/test-results/replay/inputs
if [[ -e $dst/VERIFIED ]]; then echo "inputs already verified: $dst"; exit 0; fi
mkdir -p "$dst/tendermint/config" "$dst/tendermint/data"
cp -p "$src/rebuilt/rebuilt-transactions.jsonl" "$src/rebuilt/rebuilt-transactions.jsonl.sha256" "$dst/"
cp -p "$src/step7-block-membership-2026-10-22.csv" "$dst/"
(cd "$dst" && shasum -a 256 -c rebuilt-transactions.jsonl.sha256)
cp -p "$src/extract/tendermint/config/genesis.json" "$dst/tendermint/config/"
for db in blockstore state evidence tx_index; do cp -pR "$src/extract/tendermint/data/$db.db" "$dst/tendermint/data/"; done
grep -E '  tendermint/(config/genesis\.json|data/(blockstore|state|evidence|tx_index)\.db/)' "$src/extract/SHA256SUMS" > "$dst/tendermint.SHA256SUMS"
(cd "$dst" && shasum -a 256 -c --quiet tendermint.SHA256SUMS)
expected=$(wc -l < "$dst/tendermint.SHA256SUMS"); actual=$(cd "$dst" && find tendermint -type f | wc -l)
[[ $expected -eq $actual ]] || { echo "file count mismatch: SHA256SUMS $expected, copied $actual" >&2; exit 1; }
shasum -a 256 "$dst/step7-block-membership-2026-10-22.csv" "$src/step7-block-membership-2026-10-22.csv"
cmp "$dst/step7-block-membership-2026-10-22.csv" "$src/step7-block-membership-2026-10-22.csv"
date -u +%FT%TZ > "$dst/VERIFIED"
chmod -R a-w "$dst"
echo "inputs verified: $expected tendermint files, jsonl sha256 ok, csv identical"
