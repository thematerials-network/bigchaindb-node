Non-consensus release: which blocks are valid does not change. Not yet run on a real network, and not approval for a
mixed-version prod rollout. See README.md, "Changes against prod".

New since the 2.2.2 baseline of this fork:

- CheckTx rejects integers outside int64 and nesting deeper than 100 levels. DeliverTx still accepts them, so a block
  holding such a transaction stops a node as before.
- The ABCI server listens on 127.0.0.1 by default (`BIGCHAINDB_ABCI_HOST` overrides it).
- The release bundle no longer holds test tools.
- API docs links point at upstream's `latest` docs.
