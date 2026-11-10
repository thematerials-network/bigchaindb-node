Non-consensus release: which blocks are valid does not change, and the node's own code is unchanged from 2.2.3.
Validators on 2.2.3 and 2.2.4 can run side by side. See README.md, "Changes against prod".

New since 2.2.3:

- PyJWT 2.15.1 is pinned in the bundle's venv, for the node recipe's write-token check (an nginx `auth_request`
  service). Nothing in BigchainDB imports it.
- A weekly pip-audit of the runtime pins runs in CI and opens an issue on a finding.
- `make bump PKG=x VERSION=y` changes one pin, in the requirements files and the `setup.py` that declares it, and
  rewrites the hashes.
