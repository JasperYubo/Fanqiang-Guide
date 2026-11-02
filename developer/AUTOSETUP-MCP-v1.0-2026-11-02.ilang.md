::ILANG::v5.0
[TYPE:engineering_handoff][PROJECT:fanqiang_guide][VERSION:1.0][LANG:en]

::OBJECTIVE{autosetup_mcp_integration}
  Deliver the approved device setup engineering book through the existing public knowledge MCP so the user's own AI can carry out authorized installation, configuration, repair and verification using its actual target-device tools.

::STATE{@STATUS, phase:integration_implemented, publication_evidence:per_deployment_private_Linux_record}
::STATE{@CONTRACT, service_version:1.2.0, book_version:1.1, tool:get_setup_book, resource:fanqiang://books/autosetup, prompt:setup_device, http:/api/agent/setup-book, download:/ai/books/fanqiang-autosetup-v1.1.ilang.md}
::STATE{@BOOK, path:apps/lookup/runtime/books/fanqiang-autosetup-v1.1.ilang.md, sha256:96425a3f6bf75c7c9ecbfdc657be74b053df2f323ba6cf5a5a621064bbabf98a}
::STATE{@RECOVERY, resume:read_this_file_then_check_git_status_and_current_release_evidence_before_repeating_actions, check:python_developer/check_apps.py, deployment:private_existing_Linux_operations_only}

::MODULE{EXECUTION_MODEL}
  [MUST] The engineering book supplies the workflow and acceptance conditions. The public MCP supplies reference information. The user's AI supplies the actual device control capability.
  [MUST] For an explicit device setup request, obtain the book first, bind to the target device, use search and get for applicable reference records, verify current official client instructions, then carry out the authorized work.
  [MUST] Merely retrieving a book grants no device permission. A remote shell or isolated browser does not imply access to the user's phone or desktop.
  [MUST] Keep search and get compatible. Do not convert public record source fields into instructions.
  [MUST] New book retrieval inputs contain no subscription, credential, arbitrary path or external URL. The public service never installs software on visitors' devices.
  [MUST] Missing device capability requires only the necessary user connection or manual action; independent authorized work continues. Repeat authorization is not required within established scope.
  [MUST] Book validation is not proof of device installation. Required unknown execution outcomes cannot pass acceptance.

::MODULE{SOURCE_AND_BUILD}
  [MUST] Maintain the approved book once under runtime/books. Tool, resource, prompt, HTTP and downloadable artifacts must return the same version and bytes.
  [MUST] Export metadata from the runtime's shared book manifest, including the digest, read-only executor boundary and not-run execution state.
  [MUST] Build AI discovery and downloadable content from repository inputs; later scheduled static rebuilds must preserve the integration.
  [MUST] Run python developer/check_apps.py from a directory outside the checkout using the locked lookup dependencies and Node.js. Verify packaged runtime and static book equality and metadata digests.
  [MUST] Validate every new I-Lang instruction body with the official validator; the engineering book must also pass ilang_book_check.

::MODULE{VALIDATION}
  [MUST] Exercise the official MCP SDK through initialize, tools/list, get_setup_book, resources/list and read, prompts/list and get, then search and get. Compare all book bodies and digests.
  [MUST] Check fixed HTTP retrieval, unsupported input rejection, body/origin bounds and unchanged old lookup behavior.
  [MUST] Validate the generated AI entry, visible download links, discovery metadata and compressed copies.
  [MUST] The opt-in developer/verify_autosetup_linux_flow.py accepts a separately verified official sing-box binary, the book path and a new evidence output. It performs no global installation or network reconfiguration.
  [MUST] Its isolated Linux fixture exercises a real SOCKS application path through Shadowsocks TCP to HTTPS with certificate validation, a controlled DNS resolver, one misconfigured port repair, disconnect and reconnect, then process and secret cleanup.
  [MUST] That fixture proves only its stated Linux application path. It does not prove Windows, macOS, Android, iOS, routers, TUN, system-wide routing, IPv6, UDP proxy paths or public node availability.

::MODULE{RELEASE}
  [MUST] Publish only the checked fixed source commit and hashed build outputs. Verify the release manifest source_inputs against current source bytes and compare the packaged runtime file set. Preserve runtime and static symlink baselines and the previous nginx configuration.
  [MUST] Validate nginx before activation and verify lookup health, old APIs, the new HTTP endpoint and all new MCP surfaces after activation.
  [MUST] Coordinate with the existing static publisher, restore its previous running state and retain a concrete rollback command in private deployment evidence.
  [MUST] Record local tests, CI, deployed versions, public retrieval evidence and remaining device coverage separately.
::ILANG::COMPLETE::
