# BigchainDB node fork

The node software of our BigchainDB network, moved to Python 3.12 and current dependencies without
changing chain behaviour, with one accepted exception: subnormal ("tiny") floats. Prod rejects them
because its gevent 20.6.2 wheel enables flush-to-zero; the fork accepts them. No copy of the chain
history contains a float. Three packages, kept at the releases prod runs:

| Folder | Package | Upstream | Base |
|---|---|---|---|
| `bigchaindb/` | BigchainDB 2.2.2 | `bigchaindb/bigchaindb` | tag `v2.2.2` |
| `cryptoconditions/` | cryptoconditions 0.8.0 | `bigchaindb/cryptoconditions` | tag `v0.8.0` + PyPI sdist |
| `bigchaindb-abci/` | bigchaindb-abci 1.0.5 | `ipdb/bigchaindb-abci` | commit `7c4760f3b2` (untagged 1.0.5) + PyPI sdist |

Tendermint stays at 0.31.5 (BigchainDB 2.2.2 accepts no other version). MongoDB 8.2 in tests.

## Git layout

1. Each upstream's full history, rewritten so its files sit under its folder, merged at the base
   above. `git log` and blame on upstream code work as usual.
2. One commit per package that makes the folder match the PyPI release prod installed (none needed
   for `bigchaindb/`: the tag is the tested baseline).
3. The fork's own changes on top, one commit per fix. `git diff 221c104a` shows everything the
   fork changes against what prod runs (`221c104a` is the last "Match … PyPI sdist" commit).

## Changes against prod

- `bigchaindb/web/websocket_server.py`: `asyncio.Queue()` without `loop=`; `run_app(..., loop=loop)`.
- `bigchaindb-abci/abci_pb/**/*_pb2.py`: regenerated from the descriptors embedded in the 1.0.5
  modules (`make pb2`); wire format identical.
- `bigchaindb/web/views/base.py` (`QueryArgument`), used by the GET views and the transaction POST:
  keeps prod's argument lookup, so requests with a non-JSON body don't get 415 on current werkzeug.
  Like prod (werkzeug 2.0.1), GET ignores form bodies.
- `bigchaindb/backend/localmongodb/connection.py`: pymongo 4 credentials instead of `authenticate()`.
- `bigchaindb/config_utils.py`, `bigchaindb/setup.py`: `importlib.metadata` instead of `pkg_resources`.
- `cryptoconditions/crypto.py`: `== 'bytes'` instead of `is 'bytes'`.
- Tests adjusted for the new libraries, plus regression tests.

Not changed yet: `install_requires` in `setup.py` (2020 pins; installs use
`requirements-py312.txt`) and the MongoDB TLS branch in `connection.py`.

## Usage

Docker targets need Docker (on the Mac: `docker context use colima`, 4 CPU / 8 GiB). `make help`
lists every target.

```bash
make venv                  # .venv: pinned dependencies + the three packages (editable)
make wheels                # dist/: the three wheels
make image-new             # bdb-new-env:arm64 (ARCH=amd64 for amd64)
make test                  # fork test suites in Docker (ARCH=arm64 by default)
make image-old test-old    # prod's exact stack (amd64, emulated on Apple silicon) and upstream's suites
make diff                  # old stack vs fork: transaction corpus, HTTP API, websocket events
```

`requirements-py312.txt` pins every dependency of the tested set (61 packages, 0 known advisories
in the 2026-10-27 pip-audit scan). Output goes to `test-results/` (git-excluded).

### Expected test results

`make test`: non-abci 391 passed, 11 failed, 3 skipped; abci 99 passed, 1 failed. The failures are
known and the same on prod's stack. They are listed in `scripts/known-failures-<suite>.txt`;
`make test` fails on any other failure and reports known failures that start passing:

- `test_text_search` ×2 and `test_docs`: environment only.
- 2 + 1 tests for malformed fulfillments (pyasn1 `RecursionError` kills the ABCI connection).
- 6 tests for inputs that only rapidjson rejects (NaN/Infinity in metadata, `version: "2.0\n"`),
  which crash CheckTx/DeliverTx through `e.__cause__.message`.

These tests are expected to fail until the fork decides how to reject such input.

### Old-chain replay

`scripts/replay/` replays a copy of the old chain's blockstore through both stacks on isolated
Docker networks and compares app hashes and MongoDB contents per block. It needs the local inputs
in `~/s1seven/old-chain-work`; see the header of each script (`prepare.sh`, `side.sh`, `watch.sh`,
`collect.sh`, `compare.sh`) and `make image-iproute2`.

## Local folders (git-excluded)

- `.pristine/`: the untouched baseline sources and the two PyPI sdists (input for `make pb2`).
- `.venv/`: local Python 3.12 environment.
- `test-results/`: test, diff and replay output.
