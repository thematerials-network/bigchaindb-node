#!/bin/bash
# Installs a bundle with its install.sh in a blank ubuntu:24.04 (amd64) container without network, as the node
# recipe will: only python3.12-venv and the bigchaindb user are prepared first (in an image, since apt needs
# network). Then starts the installed `bigchaindb` once to show the venv works.
# Usage: scripts/bundle/test-install.sh dist/<bundle>.tar.gz
set -euo pipefail
bundle=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
[[ -f $bundle ]] || { echo "no such bundle: $1" >&2; exit 1; }

# The three fork wheels must ship their licence files (restored upstream LICENSE files + license_files in setup.py).
unpacked=$(mktemp -d)
trap 'rm -rf "$unpacked"' EXIT
tar -C "$unpacked" -xzf "$bundle"
for pkg in bigchaindb cryptoconditions bigchaindb_abci; do
  whl=$(ls "$unpacked"/*/wheels/"$pkg"-*.whl)
  python3 -m zipfile -l "$whl" | grep -q -E 'dist-info/(licenses/)?LICENSE' || { echo "FAIL: wheel $pkg carries no LICENSE" >&2; exit 1; }
done
echo "--- licence files present in the three wheels"

# docker run + commit, as scripts/old-env/build-image.sh: the legacy builder mixes up per-platform base layers.
docker rm -f bdb-blank-node-build >/dev/null 2>&1 || true
docker run --name bdb-blank-node-build --platform linux/amd64 ubuntu:24.04 bash -c \
  'apt-get update -qq && apt-get install -y -qq --no-install-recommends python3.12-venv >/dev/null && rm -rf /var/lib/apt/lists/* && useradd -m bigchaindb' >/dev/null
docker commit bdb-blank-node-build bdb-blank-node:ubuntu24.04 >/dev/null
docker rm bdb-blank-node-build >/dev/null

docker run --rm --platform linux/amd64 --network none -v "$bundle:/bundle.tar.gz:ro" bdb-blank-node:ubuntu24.04 bash -c '
  set -euo pipefail
  mkdir /tmp/bundle && tar -C /tmp/bundle --strip-components=1 -xzf /bundle.tar.gz
  touch /tmp/before-install
  echo "--- install.sh (no network)"
  /tmp/bundle/install.sh
  echo "--- files written outside the venv by install.sh (stdlib .pyc files come from byte-compilation, not from the bundle):"
  stray=$(find / -xdev -newer /tmp/before-install -type f 2>/dev/null | grep -v "^/home/bigchaindb/venv/\|^/tmp/\|^/root/.cache/\|^/usr/lib/python3.12/.*__pycache__/" || true)
  [[ -z $stray ]] || { echo "$stray"; echo "FAIL: install.sh wrote outside the venv" >&2; exit 1; }
  echo none
  owner=$(stat -c %U:%G /home/bigchaindb/venv)
  echo "--- owner: $owner, $(/home/bigchaindb/venv/bin/python --version)"
  [[ $owner == bigchaindb:bigchaindb ]] || { echo "FAIL: venv owned by $owner, not bigchaindb" >&2; exit 1; }
  echo "--- bigchaindb start as user bigchaindb (no MongoDB here: must fail to connect, not to import)"
  output=$(su bigchaindb -c "cd && /home/bigchaindb/venv/bin/bigchaindb -y configure localmongodb >/dev/null && timeout 20 /home/bigchaindb/venv/bin/bigchaindb start" 2>&1 || true)
  echo "$output" | tail -3
  echo "$output" | grep -q "BigchainDB Version" || { echo "FAIL: bigchaindb start did not get as far as logging its version" >&2; exit 1; }
  echo "$output" | grep -q "bigchaindb.backend.exceptions.ConnectionError" || { echo "FAIL: bigchaindb start did not fail on the MongoDB connection" >&2; exit 1; }
  echo "--- OK"
'
