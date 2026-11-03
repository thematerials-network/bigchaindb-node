#!/bin/bash
# Runs a command in the old or new environment image with the right BigchainDB installed.
# Usage: scripts/diff/run-in-env.sh <old|new> <arm64|amd64> [docker run options --] <command...>
#   old: bdb-old-env:amd64 (PyPI BigchainDB 2.2.2, prod freeze); new: bdb-new-env:<arch> + the fork from /src.
# The fork root is mounted read-only at /src, test-results/diff at /out.
set -euo pipefail
env=$1 arch=$2
shift 2
root=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$root/test-results/diff"
opts=()
if [[ " $* " == *" -- "* ]]; then
  while [[ $1 != -- ]]; do opts+=("$1"); shift; done
  shift
fi
if [[ $env == old ]]; then
  image=bdb-old-env:amd64
  [[ $arch == amd64 ]] || { echo "old env is amd64 only" >&2; exit 1; }
  setup=true
else
  image=bdb-new-env:$arch
  setup='cp -a /src/bigchaindb /src/cryptoconditions /src/bigchaindb-abci /tmp/ && (cd /tmp && pip install -q --root-user-action=ignore --disable-pip-version-check --no-deps --no-build-isolation ./cryptoconditions ./bigchaindb-abci ./bigchaindb >/dev/null)'
fi
exec docker run --rm --platform "linux/$arch" -v "$root:/src:ro" -v "$root/test-results/diff:/out" ${opts[@]+"${opts[@]}"} "$image" \
  bash -c "$setup && cd / && \"\$@\"" bash "$@"
