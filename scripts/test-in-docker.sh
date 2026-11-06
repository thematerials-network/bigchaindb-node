#!/bin/bash
# Runs the BigchainDB test suite on Linux in Docker: against the source tree in python:3.12-slim, or, with
# BUNDLE=<bundle .tar.gz> (amd64 only), against the venv install.sh builds from that bundle in ubuntu:24.04.
# Usage: scripts/test-in-docker.sh <arm64|amd64> <non-abci|abci>     (K=<pytest -k expression> narrows the run)
set -euo pipefail

arch=$1
suite=$2
root=$(cd "$(dirname "$0")/.." && pwd)
results=$root/test-results
prefix=bdb-node-$arch-$suite
network=$prefix-net
mkdir -p "$results"
[[ ${BUNDLE-unset} != '' ]] || { echo "BUNDLE is set but empty (no bundle in dist/? make bundle first)" >&2; exit 1; }
bundle=${BUNDLE:+$(cd "$(dirname "$BUNDLE")" && pwd)/$(basename "$BUNDLE")}
if [[ -n $bundle ]]; then
  [[ -f $bundle ]] || { echo "no such bundle: $BUNDLE" >&2; exit 1; }
  [[ $arch == amd64 ]] || { echo "BUNDLE needs amd64: the bundle holds x86_64 wheels" >&2; exit 1; }
  image=ubuntu:24.04
  mounts=(-v "$bundle:/bundle.tar.gz:ro")
else
  image=python:3.12-slim
  mounts=()
fi

cleanup() {
  docker logs "$prefix-tendermint" > "$results/$prefix-tendermint.log" 2>&1 || true
  docker rm -f "$prefix-tests" "$prefix-mongodb" "$prefix-tendermint" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker network create "$network" >/dev/null
docker run -d --name "$prefix-mongodb" --network "$network" --network-alias mongodb mongo:8.2 >/dev/null

if [[ $suite == abci ]]; then
  marker=abci
  # Block max_bytes 64 kB: tests/tendermint/test_check_tx_integration.py needs two transactions that fit one block only one at a time.
  docker run -d --name "$prefix-tendermint" --network "$network" --network-alias tendermint \
    --platform linux/amd64 --restart always --entrypoint sh tendermint/tendermint:v0.31.5 \
    -c 'tendermint init && sed -i "s/\"max_bytes\": \"22020096\"/\"max_bytes\": \"65536\"/" /tendermint/config/genesis.json && grep -q 65536 /tendermint/config/genesis.json && tendermint node --consensus.create_empty_blocks=false --proxy_app=tcp://bigchaindb:26658' >/dev/null
else
  marker='not abci'
fi

docker run --name "$prefix-tests" --network "$network" --network-alias bigchaindb \
  --platform "linux/$arch" \
  -v "$root:/src:ro" -v "$results:/results" ${mounts[@]+"${mounts[@]}"} \
  -e BIGCHAINDB_DATABASE_BACKEND=localmongodb \
  -e BIGCHAINDB_DATABASE_HOST=mongodb \
  -e BIGCHAINDB_DATABASE_PORT=27017 \
  -e BIGCHAINDB_TENDERMINT_HOST=tendermint \
  -e BIGCHAINDB_TENDERMINT_PORT=26657 \
  -e BIGCHAINDB_SERVER_BIND=0.0.0.0:9984 \
  -e BIGCHAINDB_WSSERVER_HOST=0.0.0.0 \
  -e BIGCHAINDB_WSSERVER_ADVERTISED_HOST=bigchaindb \
  -e "MARKER=$marker" -e "K=${K:-}" -e "LOG=/results/$prefix.log" -e "FROM_BUNDLE=${bundle:+yes}" \
  "$image" bash -c '
    set -euo pipefail
    if [[ -n $FROM_BUNDLE ]]; then
      apt-get update -qq && apt-get install -y -qq --no-install-recommends python3.12-venv >/dev/null
      mkdir /tmp/bundle && tar -C /tmp/bundle --strip-components=1 -xzf /bundle.tar.gz
      /tmp/bundle/install.sh /opt/venv
      export PATH=/opt/venv/bin:$PATH
      # The bundle holds no test tools; they go on top in this container only.
      pip install -q --disable-pip-version-check --require-hashes --no-deps -r /src/requirements-py312-test.txt
      pip check
      # Only the tests and pytest.ini: with the source package beside them, pytest would import it instead of the venv.
      mkdir /tmp/suite && cp -a /src/bigchaindb/tests /src/bigchaindb/pytest.ini /tmp/suite/ && cd /tmp/suite
    else
      cp -a /src/bigchaindb /src/cryptoconditions /src/bigchaindb-abci /src/requirements-py312.txt /tmp/
      cd /tmp
      /src/scripts/install-requirements.sh pip requirements-py312.txt -q --root-user-action=ignore --disable-pip-version-check
      pip install -q --root-user-action=ignore --disable-pip-version-check --require-hashes --no-deps -r /src/requirements-py312-test.txt
      pip install -q --root-user-action=ignore --disable-pip-version-check --no-deps --no-build-isolation \
        ./cryptoconditions ./bigchaindb-abci ./bigchaindb
      cd /tmp/bigchaindb
    fi
    python -c "import platform, sys; print(platform.machine(), sys.version)" > "$LOG"
    PYTHONPATH=/tmp python -c "import bigchaindb; print(\"bigchaindb from\", bigchaindb.__file__)" >> "$LOG"
    [[ -z $FROM_BUNDLE ]] || grep -q "^bigchaindb from /opt/venv/" "$LOG" || { echo "FAIL: tests would not run against the bundle venv" >&2; exit 1; }
    python -c "from google.protobuf.internal import api_implementation as a; print(\"protobuf\", a.Type())" >> "$LOG"
    # No Hypothesis deadline: timing under amd64 emulation is not a test result.
    printf "from hypothesis import settings\nsettings.register_profile(\"no_deadline\", deadline=None)\nsettings.load_profile(\"no_deadline\")\n" > /tmp/no_deadline.py
    PYTHONPATH=/tmp python -m pytest -p no:cacheprovider -p no_deadline -q -rfEs -W ignore -m "$MARKER" -k "$K" >> "$LOG" 2>&1 || true
    tail -1 "$LOG"
  '

log=$results/$prefix.log
grep -qE '[0-9]+ (passed|failed)' <(tail -1 "$log") || { echo "pytest did not finish, see $log" >&2; exit 1; }
actual=$( (grep -E '^(FAILED|ERROR) ' "$log" || true) | sed -E 's/^(FAILED|ERROR) ([^ ]+).*/\2/' | sort -u)
known=$( (grep -v '^#' "$root/scripts/known-failures-$suite.txt" || true) | sort -u)
unexpected=$(comm -23 <(echo "$actual") <(echo "$known") | grep -v '^$' || true)
now_passing=$(comm -13 <(echo "$actual") <(echo "$known") | grep -v '^$' || true)
[[ -z $now_passing ]] || printf 'Known failures that now pass (update scripts/known-failures-%s.txt):\n%s\n' "$suite" "$now_passing"
[[ -z $unexpected ]] || { printf 'Unexpected failures:\n%s\n' "$unexpected" >&2; exit 1; }
