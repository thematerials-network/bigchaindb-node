#!/bin/bash
# Builds bdb-old-env:<arch> with docker run + commit (the legacy builder mixes up per-platform base layers).
# Usage: scripts/old-env/build-image.sh   (amd64 only, see install.sh)
set -euo pipefail
arch=amd64
dir=$(cd "$(dirname "$0")" && pwd)
name=bdb-old-env-build-$arch
docker rm -f "$name" >/dev/null 2>&1 || true
docker run --name "$name" --platform "linux/$arch" -v "$dir:/in:ro" python:3.9.25-slim-bookworm \
  bash -c 'mkdir -p /opt/old-env && cp /in/requirements.txt /in/build-constraints.txt /in/install.sh /opt/old-env/ && bash /opt/old-env/install.sh'
docker commit "$name" "bdb-old-env:$arch" >/dev/null
docker rm "$name" >/dev/null
docker run --rm --platform "linux/$arch" "bdb-old-env:$arch" python -c 'import platform, sys; print(platform.machine(), sys.version)'
