#!/bin/bash
# Installs the BigchainDB node fork from the release bundle this script sits in: a Python 3.12 venv with the
# tested dependency set (requirements-py312.txt) and the three wheels, all from wheels/, offline.
# Usage: ./install.sh [venv directory]      (default /home/bigchaindb/venv; must not exist yet)
# Upgrades install into a new versioned directory and switch a symlink afterwards; nothing is ever deleted here.
# Requires Ubuntu 24.04 on x86_64 with python3.12 and its venv module (apt package python3.12-venv).
# Writes nothing but the venv (owned by user bigchaindb when run as root and that user exists). systemd units,
# MongoDB and Tendermint are the node recipe's job.
set -euo pipefail

bundle=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
venv=${1:-/home/bigchaindb/venv}

fail() { echo "install.sh: $*" >&2; exit 1; }

[[ $(uname -m) == x86_64 ]] || fail "this bundle holds x86_64 wheels, this host is $(uname -m)"
command -v python3.12 >/dev/null || fail 'python3.12 not found (apt-get install python3.12 python3.12-venv)'
python3.12 -c 'import ensurepip' 2>/dev/null || fail 'python3.12 has no venv module (apt-get install python3.12-venv)'
[[ -d $(dirname "$venv") ]] || fail "parent directory of $venv does not exist (create the bigchaindb user first)"
[[ ! -e $venv && ! -L $venv ]] || fail "$venv already exists; install into a new directory (e.g. $venv-<version>) and switch the symlink afterwards"

(cd "$bundle" && sha256sum --quiet -c SHA256SUMS) || fail 'bundle checksums do not match'

python3.12 -m venv "$venv"
"$venv/bin/pip" install --quiet --no-index --find-links "$bundle/wheels" -r "$bundle/requirements-py312.txt"
"$venv/bin/pip" install --quiet --no-index --no-deps --find-links "$bundle/wheels" \
  cryptoconditions==0.8.0 bigchaindb-abci==1.0.5 bigchaindb==2.2.2
"$venv/bin/pip" check >/dev/null || fail 'pip check failed'
"$venv/bin/python" -c 'import bigchaindb, cryptoconditions, abci; from bigchaindb.web import server'

if [[ $(id -u) == 0 ]] && id bigchaindb >/dev/null 2>&1; then
  chown -R bigchaindb: "$venv"
fi
echo "installed $("$venv/bin/bigchaindb" --version) into $venv ($(cat "$bundle/BUNDLE"))"
