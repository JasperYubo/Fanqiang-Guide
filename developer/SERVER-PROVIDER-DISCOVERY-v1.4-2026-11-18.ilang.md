::ILANG::v5.0::ENGINEERING_BOOK

::STATE{@BOOK, id:"huarun-provider-discovery", version:"1.4", date:"2026-11-18", language:"zh-CN"}
::STATE{@SOURCE, runtime:"apps/server/provider_discovery.py 与 generic_provider.py", configuration:"/etc/huarun/network.json", state:"/var/lib/huarun-network/provider/discovered", protocol:"本机受控声明式 HTTP 接口"}
::OBJECTIVE{generic_provider_recovery}
  未知 VPS 厂商先查官方文档，有可用换 IP API 时自动生成、验证并启用适配；核实无 API 才通知用户手工换 IP。现成厂商适配器是快速路径，不构成支持范围上限。
  [ACCEPT] Linux 自动发现、来源证据、凭据隔离、只读实例验证、受控换 IP、丢失响应对账、DNS 提交与恢复闭环有可检查测试结果；fixture 与真实云资源测试分开。

::MODULE{DISCOVERY}
  [STEP:1] 读取本机已保存厂商名、可选官网、实例、区域和授权；已有用户在 SSH 终端 provider-setup 单独补充，保存后自动发现，不重装或重交 Cloudflare 令牌；配置缺少条件时报告具体字段，保留原节点及地址来源。
  [STEP:2] 先查询华润 MCP，资料不足再用 DeepSeek 搜索定位官方页面，抓取原文并记录来源与摘要。凭据值不进入模型、搜索查询、公开 MCP 或输出。
  [STEP:3] 根据官方文档生成声明式适配，检查允许的 API 来源、动作、参数、认证方式和费用条件；只读核验实例身份与入站地址，通过后保存 profile 与 receipt。文档只是证据，不能授予资源删除或任意命令权限。
  [STEP:4] huarun network provider-discover、network check 与 Linux 定时器共享发现流程；huarun network provider-status 仅返回脱敏状态，缓存减少重复查询。
  [MUST] ready、no_api_documented、documentation_unavailable、documentation_incomplete、identity_unconfirmed、credentials_required、parameters_required、adapter_contract_unsupported、adapter_validation_failed 分别处理。资料不完整先用剩余搜索额度定向补查官方说明；未知结果、不可达、身份未证实和无法表达签名都不是无 API。

::MODULE{EXECUTION}
  [MUST] 已有厂商适配器继续按原产品条件运行；未知厂商经验证的适配仍要满足保存的自动恢复授权、次数与费用预算以及有效独立地区故障证据。
  [MUST] 根目录和状态文件使用 root 私有权限。配置升级保留秘密和已验证档案；普通更新不改变节点、白名单、Key 或域名。
  [MUST] 每个变更先落盘事务，再调用 API；丢失响应先对账，不能盲目重发分配。获取新地址后独立验证、提交并读回 DNS；失败回滚或保留事务明确通知。
  [MUST] 只有官方明确否认且保存可核对原文证据时才能给 no_api_documented；读取状态失败、生成失败或限流必须保持真实错误状态。

::MODULE{RUBRIC}
  [MUST] A1: 使用至少两个无内置厂商名的测试接口走自动发现、生成、校验、只读绑定、换 IP 和 DNS 闭环，不靠厂商字符串分支通过。
  [MUST] A2: 覆盖无 API 原文、不可达、缺凭据、身份不符、恶意页面、密钥隔离、非法端点、请求失败与丢失确认；失败状态不能冒充 ready。
  [MUST] A3: Linux 新安装与旧版升级保留原配置、白名单、Key 和新增适配档案；MCP、主站、Pages 与 Release 对应同一版本。
  [MUST] A4: 当前版本工程书经官方 iLang 语法和 A1/A2 书本检查通过；发布必须经现有完整 Linux 安装升级门槛，不能用文档验证替代功能验收。

::ILANG::v5.0::ENGINEERING_BOOK
