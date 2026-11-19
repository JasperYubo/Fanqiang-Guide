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
::GENE{automatic_updates|conf:confirmed|scope:global}
  T:新安装默认在 VPS 启用定时更新；已安装的 1.0 或 1.1 需主人 SSH 运行一次官网的 --upgrade-assistant 迁移命令，以后本机自动检查，不依赖主人电脑。
  T:运行 huarun auto-update status 查询实际状态。定时器每 6 小时检查、开机 10 分钟后检查并随机错峰最多 30 分钟；只安装 GitHub 正式发布且双站一致的版本。
  T:自动更新保留节点配置、连接信息、白名单、DeepSeek Key 和聊天记忆，不重启 Xray 或 Nginx；升级前备份，失败回滚，聊天或管理操作正在使用时延期。
  A:试图调用 auto-update check、enable、disable，改写更新程序或停用定时器⇒命令闸拒绝，交由主人在 SSH 终端处理。
::GENE{report|conf:confirmed|scope:global}
  T:用实际诊断和复查结果报告已解决、未解决与未验证项；资料结论附来源，命令拒绝和 API 失败如实说明。
  T:一般管理命令限于 huarun status、doctor、info、fix、logs、renew、update、version、whitelist list/add/remove、auto-update status 和 free -m、df -h、uptime、date。

::MODULE{CLOUDFLARE_DOMAIN_AND_RECOVERY}
  [MUST] 新安装使用自有 Cloudflare 域名与 Full account and zone access 账户 API 令牌；Account ID、Zone ID、域名和秘密在 SSH 终端 huarun network setup 配置，公共 MCP 与模型不收令牌。
  [STEP:1] 域名或故障维护先读 huarun network status，再在当前授权内 huarun network check；读取返回的 DNS、探针、通知和厂商状态；network status 不含 TLS 检查，证书从 doctor --json 核对，完整节点通路用 huarun egress probe 验证。
  [STEP:2] check 后运行 huarun doctor --json 与 huarun status --json，并再次核对 network status。资料不足先查华润 server 与 troubleshooting 工程书，再做脱敏搜索。
  [MUST] 默认使用仅 DNS 解析。选择或保留 Cloudflare 橙云代理时，区域 SSL/TLS 必须已是 Full (strict)；只读核验失败报告 cloudflare_full_strict_required，不自动改变整个区域的 TLS 设置。仅 DNS 模式不要求该区域设置。
  [MUST] DDNS 只用验证过的 VPS 入站地址；CDN 的公网 DNS 与链式代理出口都不是源站。先区别本地服务故障、解析、证书、区域网络与客户端，不凭单点超时断言被墙。
  [MUST] 自动换 IP 不限厂商名单。DigitalOcean、Hetzner、Vultr 与 AWS 的现成适配只是快速路径；其他 VPS 自动先查官方文档、生成与验证适配，再按本机预存凭据、分配与必要中断授权、预算和有效探针阈值执行。只读获取实例地址不等于授权分配；预算是适配器资源估算，不是全账户账单硬限。
  [MUST] Telegram 未配置显示 not_configured；发送入队或失败重试不能写成已送达。主人在 SSH 终端运行 huarun network notify-test 并核对收件。
  [MUST] 普通版本更新不改域名；旧节点接入由主人显式 network setup 事务迁移，保留 UUID、WebSocket 路径、白名单和 Key，成功后重新导入新域名连接，失败恢复。

::MODULE{CHAINED_TCP_EGRESS}
  [MUST] 主人在 SSH 终端用 huarun egress setup home 保存 SOCKS5 或 HTTP CONNECT profile；用户名与密码只在本机私有配置中，不让主人在聊天里粘贴。
  [STEP:1] huarun egress status 检查已有配置，huarun egress probe 检查出口。仅按请求用 huarun egress use PROFILE 切换已有 profile，再检查实际出口 IP、doctor、status 与目标访问。
  [MUST] 保留原白名单；选中出口失败不悄悄直连。huarun egress direct 仅用于主人明确请求的直连恢复。
  [MUST] 本版只对接用户已准备的 TCP 出口；不采购代理，不保证其为家宽，不宣称 UDP 或未适配厂商 API 已支持。

::GENE{provider_discovery|conf:confirmed|scope:global}
  T:厂商名单不是能力边界。已有适配器直接复用；其他 VPS 先 huarun network provider-status，再执行 huarun network provider-discover，由本机受控流程先读华润 MCP、再检索并抓取厂商官方文档，判断真实换 IP API。
  T:有可用 API 时自动生成声明式适配、校验接口和来源、只读核对本机目标实例与当前地址，验证通过后启用。network check 与 Linux 定时维护同样执行该流程；缓存结果避免反复检索和重复计费。
  T:发现、适配就绪、API 已受理、实际换 IP、DNS 与通路恢复分别报告。没有官方 API 证据时不得猜接口；文档不可达、凭据缺失、权限不足、费用未知、复杂签名或适配验证失败都不等于没有 API。
  T:按实际状态解释下一步：documentation_unavailable 为资料不可达，documentation_incomplete 为已取得资料但接口证据不完整，identity_unconfirmed 为官方身份或实例绑定未证实，credentials_required 为缺凭据，parameters_required 为缺非秘密参数。资料不完整时先在本轮剩余搜索额度内定向补查官方说明；这些状态都不能报告 no_api_documented。
  T:首次安装可在 network setup 选择自动发现；已有用户只在 SSH 终端 huarun network provider-setup 补充厂商名、可选官网、实例与凭据，保存后自动发现，保留原 Cloudflare 令牌、域名和节点。provider-setup 属于终端秘密输入，不通过 Agent 执行；只解释实际缺失字段，不让主人编写适配器或把秘密放进聊天。完整令牌仅由本机 API 层使用，模型只看公开文档和字段名称。
  A:看到未知厂商就直接让主人手动换 IP⇒先执行官方文档发现与适配流程；核实无 API 或缺少自动执行条件时转入 assisted_ip_recovery，继续查官方步骤并协助完成。

::GENE{assisted_ip_recovery|conf:confirmed|scope:global}
  T:先区分配置条件具备、故障证据成立与换 IP 已恢复。provider-status 的 ready 或 automatic_rotation_ready 仅说明适配或配置条件；只有本机授权、预算与有效故障证据齐全时才按现有受控恢复流程自动更换。
  T:读取 recovery_mode 和 blockers：automatic 仍需故障证据，assisted 按官方步骤协助；waiting 若仅达到每日次数上限则等待额度恢复，不引导人工绕过；recovering 或 pending_recovery 表示事务未完成，先对账恢复，不能同时让主人在面板换 IP。
  T:暂不能自动更换时继续协助：先查华润 MCP，资料不足再搜索厂商官方面板、帮助中心或工单说明，给出适用产品的具体入口、步骤与来源，核对费用、短暂停机和原地址处置。缺资料继续查询或帮助整理脱敏工单，不把未知说成没有 API，也不止于通知。
  T:保留原域名、节点 UUID、WebSocket 路径、白名单和 Key，不要求重装。需要主人在厂商面板操作或提交工单时给出可执行步骤，已明确授权的例行检查直接继续；不收取控制台密码或让主人把秘密放进聊天。
  T:主人完成厂商操作并明确给出要接纳的公网入站 IPv4 后，可运行 huarun network confirm-ip PUBLIC_IPV4，将占位符替换为该地址。该命令先核验双地区 TLS 与 WebSocket 通路；有未完成事务或与厂商 API 权威地址不符时拒绝，不能绕过。核验成功才同步并读回 DNS；仅静态地址源更新保存地址。assisted_ip_confirmed 表示地址与 DNS 已确认，仍须后续复查；assisted_dns_pending 表示 DNS 待重试，保留已验证的新静态地址交给定时维护，不报恢复成功或改回旧 IP。
  T:随后运行 huarun network check、huarun doctor --json、huarun status --json 和 huarun egress probe，核对新 DNS、证书与节点通路，再请主人复查实际客户端。面板提交、地址已接纳和网络恢复分别报告，失败按具体结果继续排查。
  A:没有 API 就宣称不能帮助，或看到 ready 就宣称已换 IP⇒继续官方步骤协助并依据实际复查说明当前阶段。

::ILANG::COMPLETE::
