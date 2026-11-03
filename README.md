# BigchainDB node fork

The node software of our BigchainDB network, moved to Python 3.12 and current dependencies without
changing chain behaviour, except where listed under "Changes against prod". Three packages, kept at
the releases prod runs:

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

Behaviour:

- `bigchaindb/core.py`: CheckTx and DeliverTx catch any unexpected exception from decoding or
  validation, log it with the transaction id when the input decoded to one, and answer Tendermint
  with `CodeTypeInternalError = 2` (`CodeTypeError = 1` stays for invalid transactions). Prod raises
  through the ABCI server instead: the mempool connection dies, Tendermint exits at the next commit,
  and a block holding such an input halts the node. One exception: a database error in DeliverTx
  (`BackendError`, or a raw pymongo error escaping through a lazily consumed cursor) still
  propagates and crashes the ABCI server as on prod, because it is not deterministic; answering code 2 would commit an app hash the other validators do not have
  (astra review 2026-11-02). Over the HTTP API nothing changes: the web
  process validates first and answers 500 as before. Code 2 is visible on Tendermint's RPC only;
  BigchainDB's HTTP API turns every non-zero code into 500 `Transaction validation failed`.
- `cryptoconditions/fulfillment.py`: a `RecursionError` from pyasn1 while decoding a fulfillment
  (new.thematerials.network#8, `'0' * 64`) is an `ASN1DecodeError`, so BigchainDB rejects the
  transaction as `InvalidSignature` (code 1; HTTP 400 instead of prod's 500).
- `bigchaindb/lib.py`: the log line for inputs that rapidjson rejects and jsonschema accepts
  (NaN, Infinity, `version: "2.0\n"`) no longer raises `AttributeError`; the transaction is
  rejected as `SchemaValidationError` (code 1). The web view at `views/transactions.py:84` keeps
  the same `e.__cause__.message` bug, so over HTTP these still get 500 as on prod.
- Subnormal floats (`0 < |x| < 2.2250738585072014e-308`, `common/transaction.py`
  `has_subnormal_float`, checked in `Transaction.validate_id`): rejected with the same `InvalidHash`
  message prod produces. Prod rejects them by accident: its gevent 20.6.2 wheel enables
  flush-to-zero in the ABCI process, the float re-serializes as `0.0` and the id check fails. The
  explicit rule keeps old and new validators in agreement (decided 2026-11-02). No copy of the
  chain history contains a float. Over HTTP such a transaction gets 400 `InvalidHash` (prod: 500
  `Transaction validation failed`, because only prod's ABCI process has flush-to-zero). Known
  difference, not handled: a transaction signed with `0.0` whose wire bytes were then edited to a
  subnormal was accepted by prod (flushed back to `0.0`, id matches) and is rejected here.
- `bigchaindb/web/server.py`: a request with undecodable JSON gets werkzeug 2.0's 400 message
  `Failed to decode JSON object: <decoder error>` back (Flask ≥ 2.3 hides the detail outside
  debug mode).
- Accepted API text differences (spike spec §7 finding F): jsonschema 4 wording in 400 bodies
  (`{} should be non-empty` for `{} does not have enough properties`, `X is not valid under any of
  the given schemas` for `X is not of type 'object'`); werkzeug 3's 404 HTML page. The `Allow`
  header order differs between runs on both sides (built from a set), not a difference.
- `bigchaindb/backend/localmongodb/connection.py`: pymongo 4 `tls*` options in the TLS branch;
  pymongo 4 reads the client certificate and key from one PEM file, so `database.keyfile` must
  equal `database.certfile` (else `ConfigurationError`); X.509 login via `authMechanism`. Prod's
  config uses neither login nor TLS.
- Not ported: Planetmint's cryptoconditions fixes (a typo and a regex, "candidates 1-2" in the
  consensus library audit). Both sit in code the node never reaches; port both together if that
  code ever becomes reachable.

Code:

- `bigchaindb/web/websocket_server.py`: `asyncio.Queue()` without `loop=`; `run_app(..., loop=loop)`.
- `bigchaindb-abci/abci_pb/**/*_pb2.py`: regenerated from the descriptors embedded in the 1.0.5
  modules (`make pb2`); wire format identical.
- `bigchaindb/web/views/base.py` (`QueryArgument`), used by the GET views and the transaction POST:
  keeps prod's argument lookup, so requests with a non-JSON body don't get 415 on current werkzeug.
  Like prod (werkzeug 2.0.1), GET ignores form bodies.
- `bigchaindb/backend/localmongodb/connection.py`: pymongo 4 credentials instead of `authenticate()`.
- `bigchaindb/config_utils.py`, `bigchaindb/setup.py`: `importlib.metadata` instead of `pkg_resources`.
- `cryptoconditions/crypto.py`: `== 'bytes'` instead of `is 'bytes'`.
- `install_requires` in the three `setup.py` files: the exact versions of `requirements-py312.txt`
  (BigchainDB `python_requires >= 3.12`).
- Tests adjusted for the new libraries, plus regression tests. `tests/conftest.py` starts the
  ABCI server for the `abci` tests with a `BigchainDB` whose validation raises on demand (flag
  file), and `scripts/test-in-docker.sh` sets the genesis block `max_bytes` to 64 kB, both for
  `tests/tendermint/test_check_tx_integration.py` (CheckTx against a real Tendermint 0.31.5:
  backend error → code 2 over a surviving connection, repost after recovery, mempool recheck
  eviction and resubmission, malformed inputs).

## Usage

Docker targets need Docker (on the Mac: `docker context use colima`, 4 CPU / 8 GiB). `make help`
lists every target.

```bash
make venv                  # .venv: pinned dependencies + the three packages (editable)
make wheels                # dist/: the three wheels
make image-new             # bdb-new-env:arm64 (ARCH=amd64 for amd64)
make test                  # fork test suites in Docker (ARCH=arm64 by default)
make bundle test-install   # release bundle for Ubuntu 24.04 / Python 3.12 / amd64, then install.sh in a blank container
make image-old test-old    # prod's exact stack (amd64, emulated on Apple silicon) and upstream's suites
make diff                  # old stack vs fork: transaction corpus, HTTP API, websocket events
```

`requirements-py312.txt` pins every dependency of the tested set (61 packages, 0 known advisories
in the 2026-10-27 pip-audit scan). Output goes to `test-results/` (git-excluded).

### Expected test results

`make test`: non-abci 438 passed, 3 failed, 3 skipped; abci 104 passed. The failures are known and
the same on prod's stack (`test_text_search` ×2 and `test_docs`: environment only). They are listed
in `scripts/known-failures-<suite>.txt`; `make test` fails on any other failure and reports known
failures that start passing. `K=<expression>` narrows a run (`K=test_check_tx scripts/test-in-docker.sh arm64 abci`);
the Tendermint container's log is saved next to the pytest log.

### Old-chain replay

`scripts/replay/` replays a copy of the old chain's blockstore through both stacks on isolated
Docker networks and compares app hashes and MongoDB contents per block. It needs the local inputs
in `~/s1seven/old-chain-work`; see the header of each script (`prepare.sh`, `side.sh`, `watch.sh`,
`collect.sh`, `compare.sh`) and `make image-iproute2`.

## Release bundle and `install.sh`

`scripts/bundle/build-bundle.sh` (run on Ubuntu 24.04 / Python 3.12 / x86_64; `make bundle` runs it
in an `ubuntu:24.04` container) writes `dist/bigchaindb-node-<version>-ubuntu24.04-amd64.tar.gz`:
`wheels/` (the three fork wheels and one wheel per line of `requirements-py312.txt`), `install.sh`,
`requirements-py312.txt`, `SHA256SUMS`, `BUNDLE` (commit, date, builder). `install.sh [venv]`
checks the host (x86_64, `python3.12` with the venv module, i.e. apt `python3.12-venv`) and the
checksums, then creates the venv (default `/home/bigchaindb/venv`, replacing an existing one) and
installs everything from `wheels/` offline (`pip --no-index`); it writes nothing else and chowns the
venv to `bigchaindb` when run as root. The node recipe (Ansible, `new.thematerials.network`)
prepares the user and the apt package and calls `install.sh` as one step.
`scripts/bundle/test-install.sh <bundle>` (`make test-install`) rehearses that in a blank
`ubuntu:24.04` container with the network namespace removed.

`.github/workflows/release.yml` runs `make test ARCH=amd64`, builds the bundle, runs the install
test and uploads the bundle as a workflow artifact on every push and pull request; a tag `v*`
also gets a GitHub release with the bundle attached.

## Local folders (git-excluded)

- `.pristine/`: the untouched baseline sources and the two PyPI sdists (input for `make pb2`).
- `.venv/`: local Python 3.12 environment.
- `test-results/`: test, diff and replay output.
