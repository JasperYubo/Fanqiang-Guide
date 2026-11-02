::ILANG::v5.0
[TYPE:engineering_handoff][SCOPE:PROJECT][LANG:zh][VERSION:0.1]

::OBJECTIVE{id:diagnostics_mvp|owner:user|trust:untrusted|version:1|status:active}
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

::STATE{@VERIFICATION, value:{"development_platform":"Linux","native_windows_execution":"not_performed","mobile_device_execution":"not_supported","status":"implementation_and_verification_in_progress"}}

::ILANG::COMPLETE::
