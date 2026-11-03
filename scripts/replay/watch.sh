#!/bin/bash
# Exits (printing why) as soon as a replay side finishes, fails, or a container stops. Usage: watch.sh <side>...
# side = <env>-<arch>, e.g. new-arm64 old-amd64. Progress line every 30 min to the log.
start=$(date +%s)
while true; do
  for side in "$@"; do
    prefix=bdb-replay-$side
    stopped=$(docker ps -a --filter "name=$prefix-" --filter status=exited --format '{{.Names}}')
    [[ -n $stopped ]] && { echo "$side: stopped containers: $stopped"; exit 0; }
    log=$(docker logs --tail 400 "$prefix-tendermint" 2>&1)
    grep -qE 'panic|CONSENSUS FAILURE|Error on' <<<"$log" && { echo "$side: failure"; grep -E 'panic|FAILURE|Error on' <<<"$log" | head -3 | cut -c1-300; exit 0; }
    grep -qE 'Executed block +module=state height=291054 |witching to consensus' <<<"$log" && { echo "$side: finished"; grep -E 'height=29105[34] |witching' <<<"$log" | tail -3 | cut -c1-200; exit 0; }
  done
  sleep 30
done
