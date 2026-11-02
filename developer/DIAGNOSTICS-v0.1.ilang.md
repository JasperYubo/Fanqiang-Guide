::ILANG::v5.0
[TYPE:engineering_handoff][SCOPE:PROJECT][LANG:zh][VERSION:0.1]

::OBJECTIVE{id:diagnostics_mvp|owner:user|trust:untrusted|version:1|status:complete}
  ACCEPT: 本机诊断、脱敏预览、用户主动提交及删除报告通过 Linux 端到端验证。
  NON_GOALS: 自动修改代理或网络配置；上传原始日志；自动公开案例；宣称 Windows 或手机已经实机验证。
  DONE_WHEN: 可安装客户端、独立 Linux 接收服务、源码及构建记录、回滚点和验证证据全部就绪。

::STATE{@LAYOUT, value:{"package":"apps/diagnostics","client":"src/client.mjs","measurement":"src/measure.mjs","privacy":"src/report.mjs","local_ui":"src/ui.mjs","receiver":"src/collector.mjs","contract":"contract.json"}}
::STATE{@COMMANDS, value:{"install":"npm ci --ignore-scripts","test":"npm test","build":"npm run build","local_ui":"node dist/client.mjs --web","mcp":"node dist/client.mjs --stdio","configuration":"node dist/client.mjs --print-config","receiver":"node dist/collector.mjs"}}
::STATE{@RECOVERY, value:{"working_directory":"apps/diagnostics","first_check":"git status --short","resume":"Inspect test logs and deployed version before repeating a write. Preserve received reports and deletion credentials.","production_credentials":"Remain on their original host; never place them in this repository or client package."}}

::RULE{diagnostic_complete⇒local_report_only}
::RULE{browser_preview_and_explicit_submit⇒send_frozen_structured_report}
::RULE{raw_or_redacted_logs⇒never_upload}
::RULE{unknown_report_fields⇒reject}
::RULE{failed_or_unmeasured_metric⇒null_not_zero}
::RULE{linux_lab_measurement⇒not_home_network_evidence}
::RULE{publish⇒verify_build_and_save_rollback_first}
::RULE{new_measurement_or_log_edit⇒invalidate_previous_preview}
::RULE{uncertain_submission⇒retry_same_idempotency_key}
::RULE{receiver_retention⇒maximum_30_days}

::STATE{@VERIFICATION, value:{"development_platform":"Linux","native_windows_execution":"not_performed","mobile_device_execution":"not_supported","status":"released_and_public_workflow_passed","unit_tests":63,"browser_workflow":"9 steps passed","public_workflow":"2 real linux_lab runs; one explicit submission; restart restore and remote deletion passed; no retained test report","npm_install":"offline install and real MCP protocol passed","portable_linux":"install, spaces/quotes in path, reinstall, session preservation passed","portable_windows":"packaged and statically verified only","deployment_rollback":"tested and exercised once before final successful release"}}


::STATE{@RELEASE, value:{"version":"0.1.0","url":"https://fanqiang.guide/diagnostics/","source_commit":"e4d871ecfc1ba73ff9f23f9b16b5b988e337aab8","client_sha256":"570ecfeb18d743cecdbba5a3263a4afdda68cd04c1caadedaf90ba8b3a1e8f86","collector_sha256":"90f62c2a4ee1407a5b8624fb1631c204c380b835da11c711b66e6f8501e5f30c","production_release":"/opt/fanqiang-diagnostics/releases/v0.1.0-20261102T205956Z","rollback_config":"/opt/fanqiang-diagnostics/backups/20261102T205956Z/fanqiang.conf","service":"fanqiang-diagnostics.service","database":"/var/lib/fanqiang-diagnostics/reports.sqlite","evidence_root":"/opt/fanqiang-diagnostics-v0.1/evidence"}}
::STATE{@ARTIFACTS, value:{"windows_sha256":"42388707e5e6d89a579ef8056b20fd7bd7f71f1298bbd18e146ba7ac899873d1","linux_sha256":"f24e3d956e2454a4eb7ebe883b2ef05ff32bbe117f764b9aa85abb883368f61e","npm_sha256":"213aa177865b083fdbfc9fe7bc60f3e923c842b0ade2d48e48e30c9faa24725a","public_downloads":"all three downloaded and SHA256 matched","public_check_sha256":"020a9a1b40e5dcd5ac1a8b3c0b90ffa15953a66c35f946914399a41ad0dd2679"}}
::STATE{@OPERATIONS, value:{"rollback":"Restore the saved nginx config, validate with nginx -t, reload nginx, and stop/disable fanqiang-diagnostics.service. Preserve /var/lib/fanqiang-diagnostics and user receipts. Existing main site release was not changed.","client_scope":"OS socket/TUN only; no automatic HTTP/SOCKS proxy support; fixed target and limited samples","publication":"Reports remain private; no automatic editorial publication or GA4 export","health":"https://fanqiang.guide/diagnostics-api/health"}}

::ILANG::COMPLETE::
