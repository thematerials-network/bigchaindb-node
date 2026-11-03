#!/bin/bash
# Installs a hash-locked requirements file with <pip>. setuptools goes in first from its hashed wheel, so sdists
# (logstats) build against it (--no-build-isolation) instead of in a build environment pip fills without hashes.
# Usage: scripts/install-requirements.sh <pip> <requirements file> [extra pip arguments]
set -euo pipefail
pip=$1
requirements=$2
shift 2
"$pip" install --require-hashes --no-deps --only-binary :all: "$@" -r <(sed -n '/^setuptools==/,/[^\\]$/p' "$requirements")
"$pip" install --require-hashes --no-build-isolation "$@" -r "$requirements"
