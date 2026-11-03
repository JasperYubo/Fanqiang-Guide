::ILANG::v5.0::ENGINEERING_BOOK
[TYPE:engineering_book]
[ID:FANQIANG-MERLIN]
[VERSION:1.0]
[DATE:2026-11-02]
[LANG:en]

::STATE{@USER, role:router_owner_and_decision_maker, language:Chinese, provides:desired_targets_and_existing_local_node_source, does:unavoidable_physical_access_and_trusted_secret_entry}
::STATE{@AGENT, role:the_users_AI_operator, uses:tools_bound_to_the_actual_router_and_test_clients, does:identify_match_precheck_install_configure_repair_verify_and_restore_within_active_scope}
::STATE{@KNOWLEDGE, role:read_only_public_reference_service, resource:fanqiang://books/merlin, tools:query_search_get, never:device_control_secret_storage_or_live_router_testing}
::STATE{@INPUT, FILL_TARGET:actual_router_and_LAN_test_client_binding, FILL_NEED:required_sites_apps_clients_and_split_route_policy, FILL_SCOPE:active_user_authorization, FILL_REPAIR_LIMIT:3, FILL_FOLDER:protected_local_workspace}
::STATE{@IDENTITY, public_fields:router_model_device_model_id_hardware_revision_firmware_family_firmware_branch_firmware_version_architecture_kernel_package_variant_protocol, local_only:management_address_credentials_serials_MACs_subscription_urls_configs_and_logs, missing:unknown_not_inferred}
::STATE{@RUN, location:FILL_FOLDER, contains:aliases_timestamps_versions_source_digests_changes_evidence_limits_and_restore_references, excludes:secrets_raw_logs_and_personal_traffic}
::STATE{@EVIDENCE_SCOPE, document:validated_structure_only_after_official_checks, service_interface:not_tested_by_this_document_revision, router_hardware:not_tested, installation:not_executed, LAN_DNS_IPv4_IPv6_UDP_reconnection:not_tested}
::STATE{@CANON, runtime_version:2026.10.31-6f17c3d64219, source_book_version:2.9}

::RULE{UPSTREAM|source:https://github.com/hq450/fancyss/blob/b19e82cb6a05e08990a96905353921819d44d134/README.md|value:use_the_current_official_fancyss_project_for_supported_software_center_firmware_and_platform_guidance; this_revision_observed_the_pinned_3_0_branch_sources; refresh_the_sources_before_later_installation}
::RULE{PACKAGE_VERSION|source:https://github.com/hq450/fancyss/blob/b19e82cb6a05e08990a96905353921819d44d134/packages/version.json.js|value:the_observed_packages_manifest_version_is_3_5_30_not_a_GitHub_Release_label; bind_the_selected_filename_version_platform_variant_and_published_checksum_from_the_same_official_snapshot}
::RULE{INSTALLER_GATE|source:https://github.com/hq450/fancyss/blob/b19e82cb6a05e08990a96905353921819d44d134/fancyss/install.sh|value:the_installer_checks_koolshare_directory_httpdb_skipd_kernel_architecture_and_some_exact_model_strings; a_matching_marketing_name_or_merlin_brand_alone_is_insufficient}
::RULE{BUILD_VARIANT|source:https://github.com/hq450/fancyss/blob/b19e82cb6a05e08990a96905353921819d44d134/build.sh|value:full_and_lite_are_different_artifact_contents_not_security_or_speed_ranks; lite_removes_naive_tuic_client_anytls_zig_ipt2socks_haveged_and_other_resources_in_this_snapshot; removal_of_one_binary_does_not_by_itself_prove_a_protocol_absent_from_all_remaining_cores}
::RULE{MODEL_AND_ABI|value:model_family_CPU_capability_running_userland_ABI_kernel_and_package_platform_are_distinct_facts; do_not_derive_64_bit_userland_from_a_64_bit_SoC; do_not_override_an_installer_gate_to_force_a_package}
::RULE{FIRMWARE_SOURCE|value:fancyss_model_table_links_are_upstream_references_not_firmware_artifacts_or_hardware_certification; legacy_KoolCenter_posts_links_may_no_longer_identify_the_original_release; require_independent_current_model_branch_release_and_download_evidence; unavailable_or_login_hidden_content_remains_unverified}
::RULE{JFFS|source:https://github.com/RMerl/asuswrt-merlin.ng/wiki/User-scripts|value:JFFS_can_hold_custom_scripts_and_configuration; preserve_existing_user_files_and_firmware_specific_script_settings; do_not_format_JFFS_or_clear_all_scripts_as_a_generic_plugin_fix}
::RULE{RECOVERY|source:https://www.asus.com/global/support/faq/1000814/|value:ASUS_rescue_mode_is_model_specific_recovery_not_the_normal_plugin_installation_path; use_the_exact_model_and_hardware_revision_manual_only_with_separate_recovery_scope_and_physical_access}
::RULE{DNS_BOUNDARY|source:https://curl.se/docs/manpage.html#--socks5-hostname|value:curl_socks5_hostname_or_socks5h_requests_proxy_side_name_resolution_while_plain_socks5_normally_resolves_locally; a_router_curl_probe_does_not_prove_LAN_client_DNS_or_transparent_routing}
::RULE{UDP_BOUNDARY|source:https://www.rfc-editor.org/rfc/rfc1928.html#section-7|value:SOCKS5_UDP_is_a_separate_association_and_relay_capability; TCP_or_TLS_success_does_not_establish_UDP_forwarding}
::RULE{NO_CERTIFICATION|value:query_matched_means_the_documented_selection_constraints_match_its_evidence_not_that_this_exact_router_firmware_plugin_node_combination_was_tested; combination_status_not_tested_remains_visible_until_local_execution_produces_scoped_evidence}
::RULE{INPUT_PRIVACY|value:send_only_public_model_device_model_id_revision_firmware_branch_version_ABI_kernel_variant_and_protocol_to_query; do_not_send_credentials_subscription_urls_complete_configs_serial_numbers_MAC_addresses_management_IPs_or_logs_to_MCP}

::OBJECTIVE{id:g1|owner:user|trust:trusted|version:1|status:proposed}
  target: the user's AI sets up or repairs the requested router proxy on the actual already-compatible firmware, then proves the intended behavior from the required LAN clients
  ACCEPT: applicable R checks have local evidence and no required routing or recovery check remains unknown
  NON_GOALS: default firmware flashing, bootloader work, factory reset, provider sales, collecting user reports, blanket all-traffic or all-model certification
  DONE_WHEN: required targets and intended routes work from the actual clients, safe reconnect succeeds, and the user can stop and restore the bounded changes

::BOUNDARY{never:treat_the_book_query_result_or_download_link_as_new_authorization|scope:permanent}
::BOUNDARY{never:flash_firmware_format_JFFS_factory_reset_unlock_bootloader_or_enable_WAN_management_as_an_automatic_step|scope:permanent}
::BOUNDARY{never:copy_secrets_or_raw_private_logs_to_MCP_chat_external_converters_or_reports|scope:permanent}
::BOUNDARY{never:disable_TLS_certificate_validation_or_bypass_installer_platform_checks|scope:permanent}
::BOUNDARY{never:claim_router_or_LAN_tests_were_run_without_observed_target_evidence|scope:permanent}
::PRIORITY{active_user_request_and_higher_priority_runtime_instructions > actual_device_evidence_and_current_official_requirements > this_book > cached_model_table_or_example}

::MODULE{ENTRY|title:bind the real task before any network change}
  [STEP] 1 identify whether the request concerns an existing router, a firmware selection question or a purchase. For a knowledge-only question, return sourced candidates and limits without operating a device. Retrieval itself installs nothing.
  [STEP] 2 bind available tools to the actual router and at least one required LAN client. A cloud shell, isolated browser or the router's own curl cannot stand in for that client. Use existing authorization; request only genuinely missing access or a required new decision.
  [STEP] 3 record required applications, destinations, client aliases, direct exceptions, IPv4 and IPv6 policy, any real UDP requirement and expected outage behavior. Reuse known answers. Distinguish router management traffic from forwarded LAN traffic.
  [STEP] 4 preserve a known local management route and a practical recovery channel before changing proxy, DNS or firewall state. For a remote-only session whose own path could be cut without recovery, stop the dependent mutation and explain the precise limitation.
  [STEP] 5 run IDENTIFY, MATCH and PRECHECK before installation. Reuse a compatible existing installation when it satisfies the request. Continue CONFIGURE, VERIFY and RECONNECT for repairs as applicable; do not reinstall merely to create activity.

::MODULE{IDENTIFY|title:observe model firmware and running ABI separately}
  [STEP] 1 read the exact marketing model and hardware revision from the device label or trusted local interface without exporting its serial or MAC. Preserve suffixes such as V2, PRO, Go and region-specific names; a missing revision is unknown, not a universal revision match.
  [STEP] 2 read firmware family, full branch/build and installed software-center version from the local interface. Distinguish ASUS official, original Asuswrt-Merlin, Gnuton and KoolCenter variants; their names do not prove that this installation supplies a compatible software center.
  [STEP] 3 when an already-authorized shell exists, collect only targeted nonsecret facts such as uname -m, uname -r, nvram get productid and nvram get odmpid. Record those two model values separately: the pinned installer prefers a nonempty odmpid. Never dump nvram or an entire environment into chat.
  [STEP] 4 inspect local existence and executability of /koolshare, /koolshare/bin/httpdb and /usr/bin/skipd, plus current installed plugin/core versions. A filename or firmware-name heuristic is supporting evidence, not an authenticated firmware identity.
  [STEP] 5 compare UI, label, package metadata and targeted runtime facts. Resolve discrepancies locally before selection. If the AI cannot observe a needed fact, mark it unknown and use a candidate-only result rather than inventing architecture or a compatible branch.

::MODULE{MATCH|title:use the router query as a sourced candidate filter}
  [STEP] 1 discover the current query schema and supply its router-specific public IDENTITY fields actually observed. Do not send blank guesses or private settings. The query is a conjunction of supplied constraints; read its unknowns, local_prechecks, source dates and combination_status.
  [STEP] 2 interpret matched as source-backed candidate selection, candidate or insufficient_evidence as requiring the named local/source checks, conflict as a contradictory requirement to resolve before installation, and no_record as no catalog evidence rather than proof of incompatibility. A missing hardware revision alone is not a reason to invent a ban when the upstream source has no revision restriction.
  [STEP] 3 at the pinned snapshot, arm targets armv7l on kernel 2.6; hnd targets the documented 4.1 or 4.19 environments and accepts aarch64 with an hnd_v8 recommendation; hnd_v8 requires aarch64 on 4.1 or 4.19; qca is the documented RT-AX89X 4.4 case. Recheck the actual current install script instead of broadening these snapshot conditions.
  [STEP] 4 for kernel 5.4 distinguish mtk, ipq32 and ipq64 by the exact documented model gate, not by the kernel alone. ZenWiFi_BD4 selects ipq32; the pinned ipq64 installer expects TUF_6500 while the table displays TUF-BE6500, so verify the actual local model alias. Supply device_model_id only after reading the actual nonempty odmpid or otherwise productid; a matching installer identifier can resolve that named precheck, while a guessed alias cannot. Shared binaries do not make mtk and ipq64 installation packages interchangeable.
  [STEP] 5 treat RT-AX86U versus RT-AX86U PRO, TUF-AX3000 versus TUF-AX3000 V2, and RT-AX89X's 64-bit-capable CPU versus its documented 32-bit firmware as separate cases. Model names are illustrative selection traps, not substitutes for current source and runtime observations.
  [STEP] 6 choose full only when its required components justify the available space; lite is a possible smaller choice when its actual included cores satisfy the requested protocol. The README lists NaiveProxy and TUIC as full-only additions; inspect the exact package contents for other capability questions. No variant is inherently faster or more secure.
  [STEP] 7 independently verify the current firmware release source if the installed branch is unclear. A source link behind login, a legacy /posts URL or an installer-only model not in the README does not prove an available model-specific firmware build. Do not flash a different firmware merely to make this plugin candidate fit.

::MODULE{PRECHECK|title:make installation reversible on already-compatible firmware}
  [STEP] 1 verify active scope covers this plugin installation or repair, and confirm recovery through the preserved management path. Firmware flashing or destructive recovery is a separate task; report an unsupported current firmware and its verified source options without silently changing it.
  [STEP] 2 save the existing plugin configuration and required firmware/JFFS settings through their supported local backup paths. Store backups privately with version and restore instructions; they may contain secrets. Do not assume a newer configuration can be restored into an older plugin or a different firmware branch.
  [STEP] 3 inspect JFFS mount health, writable space and inodes, temporary space, RAM and current load. Check the selected package's actual installation and temporary-space requirements and the installer's current available-space gates; archive size is not installed size and there is no model-independent safe MB threshold.
  [STEP] 4 inspect existing VPNs, transparent proxies, DNS add-ons, custom startup hooks and firewall/routing rules. Identify actual overlapping ports, DNS ownership, policy routes and interception hooks. Preserve unrelated VPNs and scripts; disable or alter only a confirmed conflicting component within the task scope, with its restore action recorded.
  [STEP] 5 fetch only the exact official package from the selected upstream snapshot, bind filename, platform, full/lite variant and observed manifest version, and compare its published checksum before installation. Published MD5 can detect mismatched/corrupt bytes but is not a digital signature; a successful checksum does not authenticate an untrusted mirror.
  [STEP] 6 inspect the fetched archive and installer locally before execution for the expected metadata and file paths. Review destructive cleanup or replacement operations, including JFFS content, and protect affected user files. Never remove platform guards, relabel a package or run an arbitrary copied installer to bypass a failed precheck.

::MODULE{INSTALL|title:use the existing software center and verified artifact}
  [STEP] 1 on already-compatible firmware, use the software center's documented offline-install workflow for the verified package. Use the current official UI and instructions; do not invent a universal endpoint, password-in-command scheme or a remote curl-to-shell pipeline.
  [STEP] 2 observe installation completion and local errors without uploading raw logs. Check the installed plugin version, platform/variant, required executable cores and settings page. A successful upload or install progress bar alone is not evidence of a working proxy.
  [STEP] 3 when updating, check current release migration requirements and backup compatibility. At the pinned README snapshot an online update preserves platform and full/lite variant; full-to-lite or lite-to-full uses the appropriate offline package. Do not equate a plugin update with a firmware update.
  [STEP] 4 if the installer rejects the kernel, ABI, model or storage, stop. Resolve the observed mismatch or restore the previous working state. Do not repeatedly try other architectures, clear JFFS wholesale or force installation as a diagnostic experiment.
  [STEP] 5 keep required software-center or platform permission interactions inside the existing authorized workflow. If only the owner can perform a physical or trusted login action, give the smallest precise handoff and continue independently where possible.

::MODULE{CONFIGURE|title:configure locally and start with a recoverable client scope}
  [STEP] 1 reuse the user's existing compatible node or local secret reference. Enter passwords, keys and subscription URLs only on the actual trusted device or its protected configuration path. If no usable node source exists, report the missing local input rather than inventing one or selecting a paid provider.
  [STEP] 2 map the exact protocol and optional transport/security settings to the installed core's current official schema. Do not infer VLESS plus REALITY, UDP capability or authentication details from a package name alone; query/search/get may supply public documentation but never receive the node configuration.
  [STEP] 3 choose the intended client list, split-route policy and DNS policy while preserving local management, required LAN services and declared direct exceptions. Begin with one authorized test client when possible; expand only after its route and DNS evidence passes.
  [STEP] 4 keep IPv4 and IPv6 behavior explicit. If the path does not support a required family, report incomplete support; a user-authorized scoped block can enforce a no-bypass policy but does not turn that family into working proxy support. Do not disable IPv6 for the whole network as an unexplained universal fix.
  [STEP] 5 start the plugin and inspect its process/listener state and only the minimal relevant local errors. Keep TLS certificate validation active and check device time when needed. Proceed to actual client verification instead of accepting a green status icon.

::MODULE{REPAIR|title:repair one evidenced fault at a time}
  [STEP] 1 classify the observed failure layer: software center/install, process/configuration, local listener, name resolution, TCP reachability, TLS/authentication, policy routing or the target application. Preserve the last known working state and record one hypothesis plus a discriminating check.
  [STEP] 2 a successful DNS lookup only proves that resolver returned an answer; it does not prove the answer is correct or the target is reachable. A lookup failure can be local resolver, routing, timeout or upstream policy. Compare a controlled hostname and the intended resolver path without declaring blocking from one symptom.
  [STEP] 3 TCP failure can arise from local routing/firewall, server address/port, remote availability or network policy. TLS failure additionally needs examination of clock, hostname/SNI, trust chain and protocol configuration. Do not classify every timeout as censorship or turn off certificate checks.
  [STEP] 4 change one relevant variable, retain only bounded redacted evidence categories in the local run record, and repeat the same failing check. Count attempts across resumes; at FILL_REPAIR_LIMIT stop blind repetition, restore failed changes and report the smallest unresolved prerequisite.
  [STEP] 5 an online core test on the router is only a router-origin test. If it passes but a LAN app fails, inspect forwarding/client policy, DNS and IPv6/UDP separately rather than reinstalling the core. Return to VERIFY after a candidate fix.

::MODULE{VERIFY|title:prove the requested behavior on each actual LAN client}
  [STEP] 1 record client alias, router/plugin/core versions, uplink, route policy, timestamp/timezone and the intended outcome. Run the user's actual requested application or destination from each required client; a router speed test, geographic IP label or single public probe is insufficient.
  [STEP] 2 correlate a controlled destination or test endpoint's observed egress with the declared direct/proxy route, using minimally scoped local route/counter evidence where available. Do not capture unrelated personal traffic. A cached result or a shared NAT address alone is inconclusive.
  [STEP] 3 test DNS separately from the downstream client. State whether system DNS, browser secure DNS, app-owned DNS or proxy-side DNS is being exercised. Use unique controlled queries and endpoint/resolver observations where available; a public DNS-leak page is supporting evidence for its own test, not proof about every app or protocol.
  [STEP] 4 test IPv4 and IPv6 independently where the client, uplink, destination and chosen path support them. An absent IPv6 path is not a passed IPv6 test. For a required no-direct-fallback policy, verify the declared behavior for each present family without silently masking an unsupported one.
  [STEP] 5 when UDP is required, exercise the actual relevant UDP application or a controlled endpoint and observe its intended path. A TCP webpage, DNS query, ping or QUIC silently falling back to TCP cannot certify arbitrary UDP. Mark no required UDP use as not_applicable with scope, and unavailable required testing as unknown.
  [STEP] 6 verify declared direct exceptions and essential LAN access, including the preserved management path. Confirm that enabling the proxy did not unexpectedly capture unrelated clients or break local services.
  [STEP] 7 record pass, fail, unknown or not_applicable for each check, its actual evidence and limits. Do not promise all-app, all-device, censorship-free or all-traffic coverage from a limited trial.

::MODULE{RECONNECT|title:prove restart behavior and leave a usable recovery path}
  [STEP] 1 within the authorized scope and while retaining control, stop then restart or disconnect then reconnect the plugin using its supported controls. Observe the requested outage behavior and return of the actual downstream targets, DNS and route policy.
  [STEP] 2 do not reboot the router merely because this module exists. If reboot/startup persistence is requested and recovery is available, test that separately; otherwise report that only plugin reconnection was observed and boot persistence remains untested.
  [STEP] 3 after failure, remove or revert only the bounded changes introduced by this run. Restore the known-compatible plugin/configuration and prior routing/DNS state from local backups; verify management and baseline access. Do not blindly restore an entire unrelated firmware or incompatible database.
  [STEP] 4 if management is lost, use the already-prepared local access path and exact model's official recovery guidance. A physical rescue/firmware restoration or factory reset may destroy settings and needs its own authorized scope; never initiate it as an automatic retry of plugin installation.
  [STEP] 5 give the owner concise start/stop, reconnection, intended client scope and local restore instructions. State exactly which client/family/protocol tests passed, which remain unknown, and whether startup persistence was tested.

::MODULE{REPORT|title:report facts and remaining work in six short Chinese lines}
  [STEP] 1 identify the actual model, observed firmware branch and running ABI, with uncertainty stated.
  [STEP] 2 name the installed or reused plugin/core version and platform/variant, plus the official selection source.
  [STEP] 3 state the requested client/application routes and DNS/IPv4/IPv6/UDP outcomes separately.
  [STEP] 4 state plugin reconnection and any separately tested reboot persistence result.
  [STEP] 5 identify the bounded changes and local rollback path without exposing secrets.
  [STEP] 6 state unresolved requirements and evidence limits; document validation and a matched query are not router hardware test results.

::RUBRIC{R1: actual router and required LAN clients are bound to available tools and authorized scope|check:human}
::RUBRIC{R2: model revision firmware branch running ABI kernel and software-center prerequisites are observed or explicitly unknown; package selection has current primary-source evidence|check:human}
::RUBRIC{R3: storage conflicts backup compatibility artifact verification and recovery path pass before mutation; no default firmware flash or destructive shortcut occurred|check:human}
::RUBRIC{R4: installed or reused local configuration serves the requested real downstream targets and intended direct/proxy routes|check:human}
::RUBRIC{R5: each required downstream DNS IPv4 IPv6 and UDP check has independent scoped evidence; unknown does not count as pass|check:human}
::RUBRIC{R6: safe plugin reconnect restores requested downstream behavior; reboot persistence is distinguished if not tested|check:human}
::RUBRIC{R7: repairs are bounded and single-variable; failed changes are restored and usable local recovery instructions are delivered|check:human}
::RUBRIC{R8: secrets stay local and metadata does not imply a certified router firmware plugin node combination|check:human}
::RUBRIC{A1: the engineering book marker opens and closes this document exactly twice|check:count|path:BOOK.md|expect:2}
::RUBRIC{A2: official ilang_validate and ilang_book_check pass with zero grammar errors and warnings|check:human}

::FALLBACK{no_actual_target_control then provide_the_verified_plan_and_exact_missing_control_without_claiming_execution|source_conflict then stop_package_mutation_and_resolve_local_identity_or_current_primary_source|unknown_required_compatibility then keep_candidate_status_and_complete_the_named_precheck|failed_recovery_access then stop_remote_network_mutation|missing_local_secret then request_trusted_local_entry_without_upload|unavailable_required_LAN_test then mark_incomplete_and_do_not_certify_all_traffic}

::ILANG::v5.0::ENGINEERING_BOOK
