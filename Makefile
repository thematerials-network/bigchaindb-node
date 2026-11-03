# Entry points for the BigchainDB node fork. Docker targets need Colima (`docker context use colima`).
ARCH ?= arm64
PYTHON ?= python3.12
VENV ?= .venv

.PHONY: help venv wheels bundle test-install images image-new image-old image-iproute2 test test-non-abci test-abci test-old diff diff-corpus diff-http diff-ws pb2 clean

help:
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | expand -t 18

venv: ## Local Python 3.12 venv with the pinned dependencies and the three packages (editable)
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q -r requirements-py312.txt
	$(VENV)/bin/pip install -q --no-deps --no-build-isolation -e ./cryptoconditions -e ./bigchaindb-abci -e ./bigchaindb

# Built from a copy: setuptools rewrites the committed sdist egg-info files in place.
wheels: ## Build the three wheels into dist/ (needs make venv)
	rm -rf dist && tmp=$$(mktemp -d) && cp -a cryptoconditions bigchaindb-abci bigchaindb "$$tmp/" \
	  && $(VENV)/bin/pip wheel -q --no-deps --no-build-isolation -w dist "$$tmp/cryptoconditions" "$$tmp/bigchaindb-abci" "$$tmp/bigchaindb" \
	  ; status=$$?; rm -rf "$$tmp"; exit $$status

bundle: ## dist/bigchaindb-node-*-ubuntu24.04-amd64.tar.gz, built in an ubuntu:24.04 amd64 container (CI runs the script directly)
	docker run --rm --platform linux/amd64 -v "$(CURDIR):/src:ro" -v "$(CURDIR)/dist:/dist" ubuntu:24.04 bash -c '\
	  set -e; apt-get update -qq >/dev/null && apt-get install -y -qq --no-install-recommends python3.12 python3.12-venv git ca-certificates >/dev/null \
	  && cp -a /src /tmp/src && git config --global --add safe.directory /tmp/src && cd /tmp/src && rm -rf dist \
	  && scripts/bundle/build-bundle.sh python3.12 && cp dist/* /dist/'

test-install: ## Install the newest bundle in dist/ with install.sh in a blank ubuntu:24.04 container, offline
	scripts/bundle/test-install.sh "$$(ls -t dist/bigchaindb-node-*-ubuntu24.04-amd64.tar.gz | head -1)"

images: image-new image-old image-iproute2 ## Build every Docker image the test harness uses

image-new: ## bdb-new-env:$(ARCH): the fork's dependencies on Python 3.12
	cp requirements-py312.txt scripts/new-env/requirements-py312.txt
	docker build -q --platform linux/$(ARCH) -t bdb-new-env:$(ARCH) scripts/new-env

image-old: ## bdb-old-env:amd64: prod's exact stack (Python 3.9.25, prod freeze), ~10 min
	scripts/old-env/build-image.sh

image-iproute2: ## bdb-iproute2:local: used by the replay to speed up the ABCI socket
	printf 'FROM debian:bookworm-slim\nRUN apt-get update && apt-get install -y --no-install-recommends iproute2 && rm -rf /var/lib/apt/lists/*\n' | docker build -q -t bdb-iproute2:local -

test: test-non-abci test-abci ## Fork test suites in Docker on $(ARCH)

test-non-abci:
	scripts/test-in-docker.sh $(ARCH) non-abci

test-abci:
	scripts/test-in-docker.sh $(ARCH) abci

test-old: ## Upstream 2.2.2 test suites against prod's stack (needs image-old)
	scripts/old-env/test-in-docker.sh non-abci
	scripts/old-env/test-in-docker.sh abci

diff: diff-corpus diff-http diff-ws ## Old stack vs fork on $(ARCH): transaction corpus, HTTP API, websocket

diff-corpus:
	scripts/diff/corpus-diff.sh $(ARCH)

diff-http:
	scripts/diff/http-diff.sh $(ARCH)

diff-ws:
	scripts/diff/ws-diff.sh $(ARCH)

pb2: ## Regenerate bigchaindb-abci's _pb2 modules from the original 1.0.5 descriptors (needs .pristine/)
	scripts/regenerate-abci-pb2.sh .pristine/bigchaindb-abci $(VENV)/bin/python

clean: ## Remove build output
	rm -rf dist
