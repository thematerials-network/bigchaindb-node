#!/bin/bash
# Builds the release bundle for Ubuntu 24.04 / Python 3.12 / x86_64: the three fork wheels, a wheel for every
# dependency in requirements-py312.txt, install.sh, requirements-py312.txt, NOTICE, SHA256SUMS and a BUNDLE stamp,
# as dist/bigchaindb-node-<version>-ubuntu24.04-amd64.tar.gz.
# Run on the target platform itself (the CI runner, or `make bundle` for a Docker build of it). Needs network.
# Usage: scripts/bundle/build-bundle.sh [python executable]   (default python3.12)
set -euo pipefail
python=${1:-python3.12}
root=$(cd "$(dirname "$0")/../.." && pwd)
version=$("$python" -c "exec(open('$root/bigchaindb/bigchaindb/version.py').read()); print(__version__)")
name=bigchaindb-node-$version-ubuntu24.04-amd64
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

[[ $(uname -m) == x86_64 ]] || { echo "build-bundle.sh: must run on x86_64, not $(uname -m)" >&2; exit 1; }
"$python" -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version' || exit 1

"$python" -m venv "$work/venv"
"$work/venv/bin/pip" install -q --disable-pip-version-check -r "$root/requirements-py312.txt"
mkdir -p "$work/$name/wheels"
# Built from a copy: setuptools rewrites the committed sdist egg-info files in place.
mkdir "$work/src" && cp -a "$root/cryptoconditions" "$root/bigchaindb-abci" "$root/bigchaindb" "$work/src/"
"$work/venv/bin/pip" wheel -q --disable-pip-version-check --no-deps --no-build-isolation -w "$work/$name/wheels" \
  "$work/src/cryptoconditions" "$work/src/bigchaindb-abci" "$work/src/bigchaindb"
# --no-build-isolation: sdist-only packages build with the venv's setuptools (pip's isolated build subprocess segfaults under qemu).
"$work/venv/bin/pip" wheel -q --disable-pip-version-check --no-deps --no-build-isolation -w "$work/$name/wheels" -r "$root/requirements-py312.txt"

cp "$root/install.sh" "$root/requirements-py312.txt" "$root/NOTICE" "$work/$name/"
printf 'commit %s, built %s on %s, %s\n' "$(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo unknown)" \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(. /etc/os-release && echo "$PRETTY_NAME")" "$("$python" --version)" > "$work/$name/BUNDLE"
(cd "$work/$name" && find wheels install.sh requirements-py312.txt NOTICE BUNDLE -type f | LC_ALL=C sort | xargs sha256sum > SHA256SUMS)

mkdir -p "$root/dist"
tar -C "$work" -czf "$root/dist/$name.tar.gz" "$name"
(cd "$root/dist" && sha256sum "$name.tar.gz" > "$name.tar.gz.sha256")
echo "dist/$name.tar.gz ($(ls "$work/$name/wheels" | wc -l | tr -d ' ') wheels)"
