::ILANG::v5.0
[TYPE:engineering_handoff][SCOPE:PROJECT][LANG:zh][VERSION:0.1]

::OBJECTIVE{id:diagnostics_discovery|owner:user|trust:untrusted|version:1|status:active}
  ACCEPT: 首页和相关排错页面提供可发现的安装入口，读者能够找到安装与主动提交报告的说明。
  NON_GOALS: 自动启动测速或提交；扩大数据采集；修改诊断客户端；改变原问答结论、来源或核对日期。
  DONE_WHEN: 源码提交、Linux 构建和浏览器检查、正式发布及线上入口验证完成，回滚与验证证据留存。

::STATE{@LAYOUT, value:{"entry_module":"apps/site/diagnostics_discovery.py","home_and_guides":"apps/site/build-site-v1.4-2026-09-13.py","answers":"apps/site/faq_pages_v10.py","installation":"apps/diagnostics/site/index.html"}}
::STATE{@RECOVERY, value:{"workspace":"/opt/fanqiang-diagnostics-discovery-2026-11-02/src","first_check":"git status --short","check":"python developer/check_apps.py --output ABSOLUTE_NEW_DIRECTORY","resume":"Read selection-evidence.json and current deployment state before repeating publication. Ensure the pSEO publisher has no in-flight source transaction before switching the static release."}}
::RULE{diagnostics_entry_click⇒installation_page_only}
::RULE{report_submission⇒explicit_local_preview_and_user_click}
::RULE{router_article⇒run_on_connected_windows_or_linux_computer}
::RULE{unrelated_or_mobile_article⇒no_embedded_diagnostics_callout}
::RULE{equivalent_faq_urls⇒same_representative_selection}
::RULE{html_entry⇒matching_markdown_entry}
::RULE{publish⇒preserve_rollback_and_resume_existing_publisher}
::STATE{@SCOPE, value:{"faq_canonical_groups":16,"faq_urls":19,"guides":["v2rayn-guide","proxy-cores","router-guide"],"navigation":["desktop","mobile","footer"],"installation_anchors":["install","submit-report"],"standalone_stylesheet":"diagnostics-entry-v0.1-2026-11-02.css","development_and_deployment":"Linux only","status":"implementation_complete_verification_pending"}}

::ILANG::COMPLETE::
