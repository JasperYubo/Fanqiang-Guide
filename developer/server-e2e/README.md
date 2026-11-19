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


## Version 1.3 network acceptance

For candidates at or above 1.3.0 the same source/run/attempt-bound report also
requires the five network/provider fault suites to run with zero skipped tests.
The new-install guest exercises these additional paths before it is discarded:

- Real acme.sh DNS-01 issuance through local Cloudflare HTTP contracts, including
  TXT creation, challenge validation, certificate CSR signing, and TXT cleanup.
- Address-change DDNS with an independent API readback and state identity check.
- Authenticated local two-region probe contracts and a synthetic Telegram HTTP
  contract: failed notification queues, delayed retry, and recovery delivery.
  These prove application behavior, not live Telegram delivery or regional reachability.
- Explicit domain migration with a real certificate and installed-node probe,
  preservation of UUID/WebSocket path/whitelist/Key, and failed issuance rollback.
- The installed Xray node routes through real authenticated SOCKS5 and HTTP
  CONNECT proxy servers to an external TLS target. The whitelist must still
  reject excluded destinations. Bad credentials and an unavailable active exit
  must fail closed while a direct control request succeeds.

Each ordinary upgrade now preserves eight files, including private
`network.json` and `egress.json` with synthetic secrets. Their before/after
SHA256, existence and permission modes are mandatory release evidence. A
separate clean 1.0 installation is upgraded with neither new configuration file
present: neither file may be invented, the network status must remain
`not_configured`, and the network timer must be enabled and running. Historical
1.2 release reports retain their original validation rules; they cannot satisfy
the 1.3 candidate gate.


Xray now uses bundled public roots by default. In this isolated CA fixture only,
the probe adapter adds the fixture CA for VMess connections to `127.0.0.1:443`
whose server name is one of the three fixed `.release.invalid` test domains.
The original production `run_probe` function and actual Xray binary execute;
certificate-chain and SAN verification remain enabled. Every run must also reject
the same node with an unknown CA and with a deliberately incorrect SAN. No
production trust setting or `allowInsecure` behavior is changed.


## Version 1.4 generic provider acceptance

A 1.4 candidate must additionally run the installed discovery and generic HTTP
interpreter against two independently generated provider names absent from the
product registry. One contract uses JSON with Bearer authentication, and the
other uses query API-key authentication with form-encoded mutations. HTTP
fixtures provide official pages, search and model answers, cloud APIs, regional
observers, and notification delivery; neither paid model inference nor a real
cloud allocation is claimed.

`generic_provider_features.py` verifies automatic discovery from `Network.run`,
MCP before fallback search, fetched source hashes, generated-profile validation,
read-only instance/IP binding before activation, local-only credentials, a
replacement followed by Cloudflare DNS write/readback, and a recovery recheck.
Separate cases distinguish an explicit official no-API statement, inaccessible
documentation, missing credentials, and malicious generated requests. An
ambiguous allocation response must be reconciled without repeating a billable
POST. Failure after the DNS write must restore the previous IP and DNS state.

All prior node/whitelist/Key/network/egress preservation checks remain. Each
upgrade also seeds and snapshots the entire
`/var/lib/huarun-network/provider/discovered` tree, including nested profiles,
receipts and transactions. Per-entry type, content hash, permissions and owner
are bound into its tree digest and must remain identical. An unconfigured legacy
installation must leave that tree absent. The 1.4 gate also requires generic
provider, discovery, network integration and updater fault suites, without skips; a historical 1.3 report cannot satisfy it.


For assistant 1.4.1 and later, the same installed generic-provider check includes
mandatory assisted recovery. After an external/manual IP change it verifies the
new address through the signed observer fixtures and real installed local-node
diagnostics, commits the static address and Cloudflare readback, and runs the
next timer iteration to prove the old address is not restored. Rejected probes,
pending setup/provider transactions and mismatched active API bindings must
leave config bytes and DNS unchanged. A transient DNS write failure must retain
the verified new address for retry while preserving all other config values,
credential bytes, node files and file permissions. Historical 1.4.0 reports do
not require this newly introduced evidence.
