#!/bin/sh
# Builds a Tendermint home once (inside tendermint/tendermint:v0.31.5): fresh config and key, original genesis, and for
# the source node the original data DBs. Never copies the original config.toml or addrbook.json (real-network peers).
# Usage: configure-tm.sh <source|replay> <proxy_app> <persistent_peers>
set -eu
role=$1 proxy_app=$2 peers=$3
[ -e /tendermint/READY ] && exit 0
chmod -R u+w /tendermint 2>/dev/null || true
rm -rf /tendermint/config /tendermint/data
tendermint init >/dev/null
cp /in/config/genesis.json /tendermint/config/genesis.json
fast_sync=true
if [ "$role" = source ]; then
  for db in blockstore state evidence tx_index; do cp -R "/in/data/$db.db" /tendermint/data/; done
  chmod -R u+w /tendermint/data
  rm -f /tendermint/data/*.db/LOCK
  fast_sync=false
fi
sed -i -e "s|^proxy_app = .*|proxy_app = \"$proxy_app\"|" -e "s|^moniker = .*|moniker = \"$role\"|" \
  -e "s|^fast_sync = .*|fast_sync = $fast_sync|" -e "s|^persistent_peers = .*|persistent_peers = \"$peers\"|" \
  -e "s|^seeds = .*|seeds = \"\"|" -e "s|^pex = .*|pex = false|" -e "s|^addr_book_strict = .*|addr_book_strict = false|" \
  -e "s|^create_empty_blocks = .*|create_empty_blocks = false|" \
  -e "s|^log_level = .*|log_level = \"main:info,state:info,blockchain:info,consensus:info,*:error\"|" \
  /tendermint/config/config.toml
grep -E '^(proxy_app|moniker|fast_sync|persistent_peers|seeds|pex|addr_book_strict|create_empty_blocks|log_level) ' /tendermint/config/config.toml
touch /tendermint/READY
