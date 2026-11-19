::ILANG::v5.0
[TYPE:engineering_handoff][PROJECT:fanqiang_guide][VERSION:1.3][LANG:en]

::STATE{@RELEASE, assistant_version:"1.3.0", mcp_version:"2.5.0", server_book_version:"1.3", status:candidate_until_verified_release}
::STATE{@IDENTITY, author:"fanqiang guide", email:"info@fanqiang.guide"}
::STATE{@SOURCE, contract:"apps/lookup/runtime/setup_book.py", book:"apps/lookup/runtime/books/fanqiang-server-v1.3.ilang.md", public_sites:"https://fanqiang.guide and https://jasperyubo.github.io/Fanqiang-Guide/"}

::MODULE{PUBLIC_CONTRACT}
  [MUST] The user explicitly selected the Cloudflare account token template Full account and zone access. Keep this exact onboarding choice across the server book, embedded iLang instructions, README, main site, Pages and MCP.
  [MUST] Enter all secrets privately through target Linux terminal setup. The controlled API layer reads local root credentials; the model and public MCP receive only redacted status.
  [MUST] Default new installation uses the owner's Cloudflare domain and DNS-01 TLS. Retain explicit legacy compatibility, not default sslip onboarding. DNS-only is default; proxied records require the zone already to use Full (strict). Read and validate without changing the entire zone setting.
  [MUST] Program upgrades preserve node, whitelist, Key, memory, domain, network credentials and egress profiles. Explicit network setup domain migration is a separate rollback-capable operation; it retains UUID and WebSocket path and requires renewed client import.
  [MUST] Publish supported provider and verification scope exactly. Only expose release-validated DigitalOcean Reserved IPv4, Hetzner Floating IPv4, Vultr Reserved IPv4 and AWS Elastic IP adapters; real API mutation, injected tests and regional connectivity are separate evidence. AWS rotation requires an existing EIP association; Vultr supports Cloud Compute, not Bare Metal. Budget figures limit adapter resource-pool estimates, not the entire account bill. Do not claim other providers work because an interface exists.
  [MUST] Chain egress accepts owner-provided SOCKS5 or HTTP CONNECT TCP profiles. The terminal setup command requires a profile name, for example huarun egress setup home. It does not provision residential services or support UDP by implication. Keep whitelist and fail closed; direct fallback requires an explicit owner request.

::MODULE{EVIDENCE_AND_RELEASE}
  [MUST] Preserve historical server books 1.0, 1.1 and 1.2 byte for byte and at their existing URLs. Pin the new book and evidence separately; never rewrite old verification as evidence for this release.
  [MUST] Validate all edited iLang using the official runtime and strict validator; also check book markers with ilang_book_check. Keep pending, fixture, live and not-tested status distinct.
  [MUST] Generate both sites and MCP manifests from setup_book.py through product_contract.py and existing builders. Regenerate Pages with developer/sync_pages_contract.py --write; the common contract contains network and egress facts.
  [MUST] Linux release acceptance must cover fresh installation, old upgrades, exact bytes and modes of preserved configuration, TLS, real allowed and blocked proxy paths, Cloudflare DNS sync, notification outcomes, domain migration rollback and egress failure behavior.
  [MUST] Only passing, source-bound evidence and matching live sites may enter the automatic Release channel. No client update from an unverified candidate. Repeat this gate for every future release.
  [MUST] Deployment, timers and maintenance run on Linux. Missing notification configuration is a visible state; outbox acceptance is not delivery.
  [MUST] Update evidence hashes after final test evidence changes, then rebuild all dependent manifests. Use repository-local Git identity for author and committer.

::MODULE{OPERATIONS}
  [MUST] network status reports maintenance state, not TLS health. Use doctor for certificate checks and egress probe for the actual installed node path.
  [MUST] Separate VPS ingress IP, CDN DNS addresses and egress proxy IP. Never write a detected chain exit to ingress DNS.
  [MUST] Repair local DNS, TLS, service and firewall faults before provider rotation. Only valid target-bound regional evidence and locally saved provider authorization permit automatic address replacement.
  [MUST] Allocation budgets, downtime approval, transaction state, DNS rollback and cleanup ownership are part of recovery. Unsupported providers notify the owner and retain existing service state.
  [MUST] Read the actual current runtime commands and tests before changing these instructions. The book is a workflow, not evidence of a successfully installed user device.

::ILANG::COMPLETE::
