# Linux release acceptance

`developer/server_release_e2e.py` executes the distributed installer without
changing its bytes inside disposable Debian 12 amd64 systemd containers. It is a
required release stage, not a substitute for the unit suites.

The acceptance matrix contains a clean candidate installation and upgrades from
pinned 1.0.0, pinned 1.1.0, and the currently designated stable GitHub Release.
The same baseline may cover multiple roles only when its exact source and
installer hashes agree. When rerunning an already published candidate, the
preceding stable release is selected instead of upgrading the candidate to itself.

The installer downloads and verifies its real PicoClaw, Xray installation script
and acme.sh dependencies. Only these external provider boundaries use fixtures:

- DeepSeek's model-list account validation accepts a synthetic test Key. No paid
  model inference is claimed or needed for an installation-preservation test.
- ACME requests go to a container-local test CA. The real, hash-pinned acme.sh
  serves an HTTP-01 challenge, generates a CSR and installs the resulting test
  certificate. The fixture verifies the HTTP-01 response before signing that CSR.

The test then exercises the real VMess/WebSocket/TLS route through Nginx and
Xray to Google's 204 endpoint. A connection to example.com must be refused by
the installed default whitelist. This uses actual outbound internet access;
public DNS/CA availability and every operating system/architecture are not
inferred from the result.

Before each upgrade, the test adds a custom node UUID, custom whitelist entry,
Key-file comment and nondefault mode, plus owner memory. After upgrading, six
files must retain their exact SHA256 and permission mode, and the Xray/Nginx
process IDs and start timestamps must remain unchanged. Health, connectivity,
version and automatic-update timer checks must pass as well.

Run on an isolated Linux worker with Docker and privileged-container support:

```sh
python3 developer/server_release_e2e.py \
  --source-sha "$(git rev-parse HEAD)" \
  --output /tmp/linux-acceptance.json
```

The checkout must be clean. The workflow keeps the output outside the source
checkout and binds it to the commit, installer hash, run ID and run attempt.
`--allow-dirty` is only for local harness development; it is forbidden in GitHub
Actions and its report cannot authorize publication.

Failures exit nonzero. Controlled stage/error information and a redacted log tail
are emitted for Linux maintenance diagnostics; full diagnostic logs are retained
in an owner-only sibling directory. The public JSON contains checks, hashes and
booleans, not Key values or node configurations. Containers are removed by their
exact generated names, including after a failed or timed-out test. No production
host ports are published, and no customer configuration is mounted.
