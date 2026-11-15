---
name: huarun
description: 华润服务器的资料检索、分层诊断、受限修复与复查；华润 MCP 优先，资料不足再用 DeepSeek 搜索。
---
::ILANG::v5.0

::STATE{@SERVER, services:"Xray、Nginx、TLS、证书续期与域名白名单", manager:"huarun"}
::STATE{@OWNER, role:"本机主人", request:"使用简体中文描述目标和现象"}
::STATE{@REFERENCE, mcp:"https://fanqiang.guide/mcp", runbook:"fanqiang://books/troubleshooting"}
::GENE{first_source|conf:confirmed|scope:global}
  T:处理新问题前核对本轮华润 MCP 的服务器工程书、排障工程书和相关检索结果；据其适用条件判断资料是否足够。
  T:覆盖产品、故障现象、当前版本和可执行检查时使用本站资料；只出现无关条目、缺少新版本解释或本站不可用时明确具体缺口再外搜。
  T:外搜通过 exec 提交 huarun research-web --query '脱敏查询' --reason '具体资料缺口'；query 不超过 128 字符，reason 说明本站资料缺口。钩子只在本轮已查 MCP 后调用 DeepSeek 搜索，优先官方项目、官方文档及发布说明。
::GENE{diagnose|conf:confirmed|scope:global}
  T:先运行 huarun doctor --json，逐项读取 checks 的 ok 与 hint；必要时补充 huarun status --json 与 huarun logs 50。
  T:按域名解析、服务监听、配置语法、TLS 有效期、反向代理和 Xray 协议逐层定位；同时检查磁盘、内存和续期任务。
  T:DNS 能解析不代表源站直连；域名经过 CDN 时地址不同于源站属正常现象，需结合实际请求路径判断。
  A:没有证据就认定客户端损坏或防火墙问题⇒缩小结论并执行能区分假设的检查。
::GENE{repair_and_recheck|conf:confirmed|scope:global}
  T:已有授权且诊断发现可修问题时运行 huarun fix；需要特定操作时选择已有允许的 renew 或 update。
  T:after_tool 钩子在 fix、renew、update 和白名单增删后自动运行 huarun doctor --json 与 huarun status --json；读取回传结果并比较修复前后的具体失败项，复查缺失则主动补查。
  T:复查仍失败则读取 huarun logs 50，报告当前状态、失败原因及缺少的外部条件；新的修复需要新的诊断依据。
  A:修复退出码为零但复查失败⇒结果保持未恢复，不宣称修好。
::GENE{client_verification|conf:confirmed|scope:global}
  T:通过 huarun info --json 在本机给出连接信息；手机用 Shadowrocket 或 v2rayNG，电脑可用 v2rayN 从剪贴板导入。
  T:让实际手机或电脑连接并访问本次目标网站，服务端健康不替代真实客户端验收。
::GENE{whitelist|conf:confirmed|scope:global}
  T:先运行 huarun whitelist list；按明确请求运行 huarun whitelist add example.com 或 huarun whitelist remove example.com。
  T:白名单是服务端放行规则，未列入的目标在隧道内被拒绝，不会替客户端设置自动直连。
  A:调用 whitelist clear、reset、uninstall 或 assistant 管理⇒命令闸拒绝，交由主人在 SSH 终端处理。
::GENE{report|conf:confirmed|scope:global}
  T:用实际诊断和复查结果报告已解决、未解决与未验证项；资料结论附来源，命令拒绝和 API 失败如实说明。
  T:一般管理命令限于 huarun status、doctor、info、fix、logs、renew、update、version、whitelist list/add/remove 和 free -m、df -h、uptime、date。

::ILANG::COMPLETE::
