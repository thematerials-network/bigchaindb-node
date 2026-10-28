#!/bin/bash
# Old-chain replay, one side. A fresh node (MongoDB + `bigchaindb start` + Tendermint 0.31.5 from the original genesis,
# no data) fast-syncs every original block from a source Tendermint node that holds the copy of the original
# blockstore/state (behind source_app.py, which only reports the stored height). Fast sync verifies each block's commit
# with the validator set the fresh node's BigchainDB produces (elections) and panics on an app hash mismatch.
# Isolation: `docker network create --internal` (no route out), no published ports, fresh Tendermint configs (only peer:
# the local source node; no seeds, pex off, addr book empty), throwaway validator keys outside the genesis set.
# Usage: scripts/replay/side.sh <old|new> <arm64|amd64> <up|status|logs|down|purge>
#   up     start or resume (volumes persist; the fresh node resumes from BigchainDB's last stored height)
#   down   remove containers and network, keep volumes;  purge  also remove volumes
# Needs image bdb-iproute2:local (debian:bookworm-slim + iproute2) for the quickack step.
# Env for up: SOURCE_APP_HASH (state AppHash at the source height, as text; learned once from a mismatch panic)
set -euo pipefail
env=$1 arch=$2 action=$3
root=$(cd "$(dirname "$0")/../.." && pwd)
inputs=$root/test-results/replay/inputs
prefix=bdb-replay-$env-$arch
network=$prefix-net
source_height=291054
containers=("$prefix-tendermint" "$prefix-bigchaindb" "$prefix-mongodb" "$prefix-source" "$prefix-source-app")
volumes=("$prefix-mongo" "$prefix-tm" "$prefix-source-tm")

remove_containers() { docker rm -f "${containers[@]}" >/dev/null 2>&1 || true; }
case $action in
  down) remove_containers; docker network rm "$network" >/dev/null 2>&1 || true; exit 0 ;;
  purge) remove_containers; docker network rm "$network" >/dev/null 2>&1 || true
         docker volume rm "${volumes[@]}" >/dev/null 2>&1 || true; exit 0 ;;
  logs) for container in "${containers[@]}"; do echo "--- $container"; docker logs "$container" 2>&1; done; exit 0 ;;
  status)
    docker ps -a --filter "name=$prefix-" --format '{{.Names}} {{.Status}}'
    docker exec "$prefix-mongodb" mongosh --quiet bigchain --eval \
      'const b = db.blocks.find().sort({height: -1}).limit(1).toArray()[0]; print(JSON.stringify({height: b && b.height, app_hash: b && b.app_hash, transactions: db.transactions.estimatedDocumentCount()}))' || true
    docker logs --tail 2 "$prefix-tendermint" 2>&1 | cut -c1-220
    exit 0 ;;
  up) ;;
  *) echo "unknown action $action" >&2; exit 1 ;;
esac

[[ -e $inputs/VERIFIED ]] || { echo "run scripts/replay/prepare.sh first" >&2; exit 1; }
remove_containers
docker network inspect "$network" >/dev/null 2>&1 || docker network create --internal "$network" >/dev/null
for volume in "${volumes[@]}"; do docker volume create "$volume" >/dev/null; done

tendermint_run() { docker run --rm --platform linux/amd64 --network none -v "$root/scripts/replay:/scripts:ro" \
  -v "$inputs/tendermint:/in:ro" --entrypoint sh "$@"; }
tendermint_run -v "$prefix-source-tm:/tendermint" tendermint/tendermint:v0.31.5 /scripts/configure-tm.sh source tcp://source-app:26658 ''
source_id=$(tendermint_run -v "$prefix-source-tm:/tendermint" tendermint/tendermint:v0.31.5 -c 'tendermint show_node_id')
tendermint_run -v "$prefix-tm:/tendermint" tendermint/tendermint:v0.31.5 /scripts/configure-tm.sh replay tcp://bigchaindb:26658 "$source_id@source:26656"

if [[ $env == old ]]; then
  image=bdb-old-env:amd64 setup=true
else
  image=bdb-new-env:$arch
  setup='cp -a /src/bigchaindb /src/cryptoconditions /src/bigchaindb-abci /tmp/ && (cd /tmp && pip install -q --root-user-action=ignore --disable-pip-version-check --no-deps --no-build-isolation ./cryptoconditions ./bigchaindb-abci ./bigchaindb >/dev/null)'
fi
wait_for_port() {
  for _ in $(seq 1 180); do
    docker exec "$1" python -c "import socket; socket.create_connection(('127.0.0.1', $2), 2)" 2>/dev/null && return 0
    sleep 2
  done
  echo "$1 not listening on $2" >&2; return 1
}

docker run -d --name "$prefix-source-app" --network "$network" --network-alias source-app --platform "linux/$arch" \
  -v "$root:/src:ro" "$image" bash -c "$setup && cd / && exec python -I /src/scripts/replay/source_app.py $source_height '${SOURCE_APP_HASH:-}'" >/dev/null
wait_for_port "$prefix-source-app" 26658
docker run -d --name "$prefix-source" --network "$network" --network-alias source --platform linux/amd64 \
  -v "$prefix-source-tm:/tendermint" tendermint/tendermint:v0.31.5 node >/dev/null

docker run -d --name "$prefix-mongodb" --network "$network" --network-alias mongodb -v "$prefix-mongo:/data/db" mongo:8.2 >/dev/null
docker run -d --name "$prefix-bigchaindb" --network "$network" --network-alias bigchaindb --platform "linux/$arch" \
  -v "$root:/src:ro" \
  -e BIGCHAINDB_DATABASE_BACKEND=localmongodb -e BIGCHAINDB_DATABASE_HOST=mongodb -e BIGCHAINDB_DATABASE_PORT=27017 \
  -e BIGCHAINDB_TENDERMINT_HOST=tendermint -e BIGCHAINDB_TENDERMINT_PORT=26657 \
  -e BIGCHAINDB_SERVER_BIND=0.0.0.0:9984 -e BIGCHAINDB_WSSERVER_HOST=0.0.0.0 \
  "$image" bash -c "$setup && cd / && bigchaindb -y configure && exec bigchaindb -l INFO start" >/dev/null
wait_for_port "$prefix-bigchaindb" 26658
docker run -d --name "$prefix-tendermint" --network "$network" --network-alias tendermint --platform linux/amd64 \
  -v "$prefix-tm:/tendermint" tendermint/tendermint:v0.31.5 node >/dev/null
# Harness speed only: ACK immediately on the internal network. BigchainDB's gevent ABCI socket has Nagle on and
# Tendermint's side delays ACKs, so each synchronous ABCI call otherwise waits ~40 ms (7 instead of ~50 blocks/s).
for container in "$prefix-bigchaindb" "$prefix-tendermint" "$prefix-source" "$prefix-source-app"; do
  docker run --rm --cap-add NET_ADMIN --network "container:$container" bdb-iproute2:local \
    sh -c 'route=$(ip route | grep -v "^default" | head -1); ip route change $route quickack 1'
done
echo "$prefix started (network $network, internal; source node id $source_id)"
