#!/bin/bash
# Starts or stops a single-validator node: mongo:8.2 + Tendermint 0.31.5 + `bigchaindb start` in the old or new env.
# Usage: scripts/diff/node.sh <old|new> <arm64|amd64> <up|down|logs>
# Host ports: old  API 19984, websocket 19985, Tendermint RPC 16657
#             new  API 29984, websocket 29985, Tendermint RPC 26657 (+10000 offset on amd64 new: 39984/39985/36657)
# REQPARSE=args-only (new only) swaps in the args-only QueryArgument inside the container (scripts/diff/reqparse_args_only.py).
# WS_FIX=run-app-loop (new only) passes loop=loop to aiohttp.web.run_app inside the container (candidate fix, not in the fork).
# BigchainDB's log goes to the container's stdout (docker logs bdb-node-<env>-<arch>-bigchaindb).
set -euo pipefail
env=$1 arch=$2 action=$3
root=$(cd "$(dirname "$0")/../.." && pwd)
prefix=bdb-node-$env-$arch
network=$prefix-net
case $env-$arch in
  old-amd64) api=19984 ws=19985 rpc=16657 ;;
  new-arm64) api=29984 ws=29985 rpc=26657 ;;
  new-amd64) api=39984 ws=39985 rpc=36657 ;;
  *) echo "unsupported: $env-$arch" >&2; exit 1 ;;
esac

down() {
  docker rm -f "$prefix-bigchaindb" "$prefix-tendermint" "$prefix-mongodb" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}

if [[ $action == down ]]; then down; exit 0; fi
if [[ $action == logs ]]; then docker logs "$prefix-bigchaindb" 2>&1; echo '--- tendermint'; docker logs "$prefix-tendermint" 2>&1; exit 0; fi

down
docker network create "$network" >/dev/null
docker run -d --name "$prefix-mongodb" --network "$network" --network-alias mongodb mongo:8.2 >/dev/null
if [[ $env == old ]]; then
  image=bdb-old-env:amd64
  setup=true
else
  image=bdb-new-env:$arch
  patch=true
  [[ ${REQPARSE:-} == args-only ]] && patch='python /src/scripts/diff/reqparse_args_only.py /tmp/bigchaindb/bigchaindb/web/views/base.py'
  [[ ${WS_FIX:-} == run-app-loop ]] && patch="$patch && sed -i \"s/port=config\['wsserver'\]\['port'\])/port=config['wsserver']['port'], loop=loop)/\" /tmp/bigchaindb/bigchaindb/web/websocket_server.py && grep -q 'loop=loop)' /tmp/bigchaindb/bigchaindb/web/websocket_server.py"
  setup="cp -a /src/bigchaindb /src/cryptoconditions /src/bigchaindb-abci /tmp/ && $patch && (cd /tmp && pip install -q --root-user-action=ignore --disable-pip-version-check --no-deps --no-build-isolation ./cryptoconditions ./bigchaindb-abci ./bigchaindb >/dev/null)"
fi
docker run -d --name "$prefix-bigchaindb" --network "$network" --network-alias bigchaindb --platform "linux/$arch" \
  -p "127.0.0.1:$api:9984" -p "127.0.0.1:$ws:9985" -v "$root:/src:ro" \
  -e BIGCHAINDB_DATABASE_BACKEND=localmongodb -e BIGCHAINDB_DATABASE_HOST=mongodb -e BIGCHAINDB_DATABASE_PORT=27017 \
  -e BIGCHAINDB_TENDERMINT_HOST=tendermint -e BIGCHAINDB_TENDERMINT_PORT=26657 -e BIGCHAINDB_ABCI_HOST=0.0.0.0 \
  -e BIGCHAINDB_SERVER_BIND=0.0.0.0:9984 -e BIGCHAINDB_WSSERVER_HOST=0.0.0.0 -e BIGCHAINDB_WSSERVER_SCHEME=ws \
  -e BIGCHAINDB_WSSERVER_ADVERTISED_HOST=localhost -e BIGCHAINDB_WSSERVER_ADVERTISED_PORT=$ws \
  -e BIGCHAINDB_WSSERVER_ADVERTISED_SCHEME=ws \
  "$image" bash -c "$setup && cd / && bigchaindb -y configure && exec bigchaindb -l DEBUG start" >/dev/null
docker run -d --name "$prefix-tendermint" --network "$network" --network-alias tendermint --platform linux/amd64 \
  -p "127.0.0.1:$rpc:26657" --entrypoint sh tendermint/tendermint:v0.31.5 \
  -c 'tendermint init >/dev/null && sed -i "s/^timeout_commit = .*/timeout_commit = \"1s\"/" /tendermint/config/config.toml && exec tendermint node --consensus.create_empty_blocks=false --proxy_app=tcp://bigchaindb:26658 --rpc.laddr=tcp://0.0.0.0:26657' >/dev/null
for _ in $(seq 1 180); do
  if curl -sf -m 2 "http://127.0.0.1:$rpc/status" 2>/dev/null | grep -q '"latest_block_height"' \
     && curl -sf -m 2 "http://127.0.0.1:$api/" >/dev/null 2>&1; then
    echo "$prefix up: API $api, websocket $ws, RPC $rpc"; exit 0
  fi
  sleep 2
done
echo "$prefix did not come up" >&2
docker logs --tail 30 "$prefix-bigchaindb" >&2
exit 1
