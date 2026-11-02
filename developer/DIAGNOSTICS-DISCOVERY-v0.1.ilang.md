::ILANG::v5.0
[TYPE:engineering_handoff][SCOPE:PROJECT][LANG:zh][VERSION:0.1]

::OBJECTIVE{id:diagnostics_discovery|owner:user|trust:untrusted|version:1|status:complete}
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
::STATE{@SCOPE, value:{"faq_canonical_groups":16,"faq_urls":19,"guides":["v2rayn-guide","proxy-cores","router-guide"],"navigation":["desktop","mobile","footer"],"installation_anchors":["install","submit-report"],"standalone_stylesheet":"diagnostics-entry-v0.1-2026-11-02.css","development_and_deployment":"Linux only","status":"complete"}}


::STATE{@RELEASE, value:{"status":"complete","source_commit":"5266d987be9309059aceada8bd80d6864b7492a1","published_at_utc":"2026-11-02T22:17:05Z","release":"/srv/fanqiang/releases/cases-v1.0-20261102T221705Z-diagnostics-entry/public","archive_sha256":"0ffe6bfcb42a324558096a3e9fcb2012fd41f69a068ec4a00f654a0e36bc2414","static_ci":"https://github.com/JasperYubo/Fanqiang-Guide/actions/runs/41535552151","diagnostics_ci":"https://github.com/JasperYubo/Fanqiang-Guide/actions/runs/41535552153","source_ci_result":"success"}}
::STATE{@EVIDENCE, value:{"root":"/opt/fanqiang-diagnostics-discovery-2026-11-02","full_check":"check-1/report.json","full_check_ok":true,"preview_browser":"evidence/discovery-preview-check.json","preview_checks_passed":24,"public_browser":"evidence/publication-browser-check.json","public_browser_sha256":"c25455ce107c2b0d8e67d04d581a9b720024cf0794c7cce782d6d30c1ef5e950","public_browser_checks_passed":21,"public_http":"evidence/public-http-check.json","public_http_checks_passed":48,"cache_purge":"evidence/cache-purge.json","cache_urls_purged":68,"deployment":"publication/deployment.json"}}
::STATE{@OBSERVATION, value:{"browser":"Linux Chromium","viewports":3,"automatic_diagnostics_requests":0,"report_submissions":0,"existing_cloudflare_rum_posts":69,"unexpected_post_requests":0,"analytics_requests_blocked_for_browser_qa":36,"download_archive_bodies_fetched":0,"scope":"The public browser run verifies navigation and absence of automatic diagnosis or report submission. Existing CDN RUM is recorded separately; this run is not a new network benchmark or proof of analytics collection."}}
::STATE{@ROLLBACK, value:{"static_before":"/srv/fanqiang/releases/seo-content-v1.1-2026-11-02/public","static_current_link":"/srv/fanqiang/current","installation_target":"/opt/fanqiang-diagnostics/releases/v0.1.0-20261102T205956Z/site/index.html","installation_backup":"/opt/fanqiang-diagnostics/backups/cases-v1.0-20261102T221705Z-diagnostics-entry/site-index.html","installation_before_sha256":"b87bf87561cfeeca21857636f46edb21dc6ba6d68629d5c8c382f31266fb1c7a","installation_after_sha256":"a2c1b7950072a2190f55128786a8aa4c4935276e027dcae9ecf8114a3ef484e8","procedure":"Check the current pointer and page hash before restoration. During a confirmed idle window stop fanqiang-pseo.service, atomically restore the recorded static pointer and installation backup only if they still match this release, verify origin responses, purge affected cache URLs, then start the publisher in a finally block. Do not overwrite a later publication or concurrent page edit."}}
::STATE{@OPERATIONS, value:{"publisher":"fanqiang-pseo.service","publisher_after_publication":"active/running","future_publications":"The publisher fetches main before rebuilding; discovery entries are versioned generator input and survive later case publications.","diagnostics_api_changed":false,"diagnostics_client_packages_changed":false,"credentials_copied":false,"handoff_hub":"/opt/fanqiang-diagnostics-discovery-2026-11-02/final-handoff.json","handoff_origin":"/srv/fanqiang/maintenance/diagnostics-discovery-2026-11-02/final-handoff.json"}}

::ILANG::COMPLETE::
