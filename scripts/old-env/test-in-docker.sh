#!/bin/bash
# Runs upstream's 2.2.2 test suite (tests from .pristine/bigchaindb = tag v2.2.2) against prod's environment
# (bdb-old-env:amd64, PyPI BigchainDB 2.2.2). Tests run outside the source tree so the installed package is tested.
# Usage: scripts/old-env/test-in-docker.sh <non-abci|abci>
set -euo pipefail
suite=$1
arch=amd64
root=$(cd "$(dirname "$0")/../.." && pwd)
results=$root/test-results
prefix=bdb-old-$arch-$suite
network=$prefix-net
mkdir -p "$results"

cleanup() {
  docker rm -f "$prefix-tests" "$prefix-mongodb" "$prefix-tendermint" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker network create "$network" >/dev/null
docker run -d --name "$prefix-mongodb" --network "$network" --network-alias mongodb mongo:8.2 >/dev/null

if [[ $suite == abci ]]; then
  marker=abci
  docker run -d --name "$prefix-tendermint" --network "$network" --network-alias tendermint \
    --platform linux/amd64 --restart always --entrypoint sh tendermint/tendermint:v0.31.5 \
    -c 'tendermint init && tendermint node --consensus.create_empty_blocks=false --proxy_app=tcp://bigchaindb:26658' >/dev/null
else
  marker='not abci'
fi

docker run --name "$prefix-tests" --network "$network" --network-alias bigchaindb \
  --platform "linux/$arch" \
  -v "$root/.pristine/bigchaindb:/src:ro" -v "$results:/results" \
  -e BIGCHAINDB_DATABASE_BACKEND=localmongodb \
  -e BIGCHAINDB_DATABASE_HOST=mongodb \
  -e BIGCHAINDB_DATABASE_PORT=27017 \
  -e BIGCHAINDB_TENDERMINT_HOST=tendermint \
  -e BIGCHAINDB_TENDERMINT_PORT=26657 \
  -e BIGCHAINDB_SERVER_BIND=0.0.0.0:9984 \
  -e BIGCHAINDB_WSSERVER_HOST=0.0.0.0 \
  -e BIGCHAINDB_WSSERVER_ADVERTISED_HOST=bigchaindb \
  -e "MARKER=$marker" -e "LOG=/results/$prefix.log" \
  bdb-old-env:amd64 bash -c '
    set -euo pipefail
    mkdir /tmp/run && cp -a /src/tests /src/pytest.ini /src/setup.cfg /tmp/run/
    python -c "import platform, sys; print(platform.machine(), sys.version)" > "$LOG"
    python -c "from google.protobuf.internal import api_implementation as a; print(\"protobuf\", a.Type())" >> "$LOG"
    site=$(python -c "import bigchaindb, os; print(os.path.dirname(bigchaindb.__file__))")
    echo "PyPI package vs tag v2.2.2 source:" >> "$LOG"
    diff -r -x __pycache__ "$site" /src/bigchaindb >> "$LOG" 2>&1 && echo "identical" >> "$LOG" || true
    cd /tmp/run
    python -m pytest -p no:cacheprovider -p no:typeguard -q -rfEs -W ignore -m "$MARKER" >> "$LOG" 2>&1 || true
    tail -1 "$LOG"
  '
