#!/bin/bash
# Step 4: builds the corpus in both environments (must be byte-identical), runs it through old and new,
# and writes the difference list. Usage: scripts/diff/corpus-diff.sh <new arch: arm64|amd64>
# Output in test-results/diff: corpus-*.json, run-*.json, compare-corpus-old-amd64-new-<arch>.txt
set -euo pipefail
arch=$1
root=$(cd "$(dirname "$0")/../.." && pwd)
run=$root/scripts/diff/run-in-env.sh
out=$root/test-results/diff
network=bdb-diff-$arch-net
cleanup() {
  docker rm -f "bdb-diff-$arch-mongodb" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup
docker network create "$network" >/dev/null
docker run -d --name "bdb-diff-$arch-mongodb" --network "$network" --network-alias mongodb mongo:8.2 >/dev/null

"$run" old amd64 python -I -W ignore /src/scripts/diff/make_corpus.py /out/corpus-old-amd64.json
"$run" new "$arch" python -I -W ignore /src/scripts/diff/make_corpus.py "/out/corpus-new-$arch.json"
cmp "$out/corpus-old-amd64.json" "$out/corpus-new-$arch.json"
echo "corpus identical ($(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))['cases']))" "$out/corpus-old-amd64.json") cases)"

for side in "old amd64" "new $arch"; do
  set -- $side
  "$run" "$1" "$2" --network "$network" -e BIGCHAINDB_DATABASE_HOST=mongodb -e "BIGCHAINDB_DATABASE_NAME=diff_$1_$2" -- \
    python -I -W ignore /src/scripts/diff/run_corpus.py /out/corpus-old-amd64.json "/out/run-$1-$2.json" 2>/dev/null | grep '^done'
done
python3 "$root/scripts/diff/compare.py" "$out/run-old-amd64.json" "$out/run-new-$arch.json" --ignore environment \
  > "$out/compare-corpus-old-amd64-new-$arch.txt" || true
tail -1 "$out/compare-corpus-old-amd64-new-$arch.txt"
