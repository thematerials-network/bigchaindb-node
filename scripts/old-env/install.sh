#!/bin/bash
# Installs prod's BigchainDB 2.2.2 environment (the prod node freeze of 2026-10-22) the way rebuild-venv.sh does.
# Runs inside python:3.9.25-slim-bookworm; scripts/old-env/build-image.sh commits the result.
# amd64 only: gevent 20.6.2 and cryptography 2.3.1 come from the same PyPI wheels prod uses. arm64 has no
# such wheels and gevent 20.6.2 cannot be compiled any more (needs Cython 3.0 alphas, gone from PyPI;
# fails with Cython 3.0.0).
set -euo pipefail
cd /opt/old-env
apt-get update -qq && apt-get install -y -qq build-essential pkg-config libssl-dev libffi-dev libevent-dev libsodium-dev >/dev/null
pip install -q --root-user-action=ignore --disable-pip-version-check pip==25.3 setuptools==80.9.0 wheel==0.45.1
[ "$(uname -m)" = x86_64 ] || { echo "old env is amd64 only" >&2; exit 1; }
PIP_CONSTRAINT=build-constraints.txt SODIUM_INSTALL=system \
  pip install -q --root-user-action=ignore --disable-pip-version-check --no-deps -r requirements.txt
pip check
# Test tools only, constrained so no runtime package moves (versions from 2020, matching 2.2.2's era).
pip freeze > runtime-freeze.txt
pip install -q --root-user-action=ignore --disable-pip-version-check -c runtime-freeze.txt \
  pytest==6.1.2 pytest-mock==3.3.1 pytest-flask==1.0.0 pytest-aiohttp==0.3.0 pytest-asyncio==0.14.0 hypothesis==5.41.0
pip freeze > freeze.txt
diff <(grep -iv '^\(pytest\|hypothesis\|iniconfig\|pluggy\|py==\|toml\|sortedcontainers\|exceptiongroup\|tomli\)' freeze.txt) runtime-freeze.txt
rm -rf /var/lib/apt/lists/* /root/.cache
