::ILANG::v5.0::ENGINEERING_BOOK

::STATE{@BOOK, id:"fanqiang-server", version:"1.0", title:"华润服务器助手安装与使用", date:"2026-11-13"}
::STATE{@OWNER, role:"用户自己的 VPS 的主人"}
::STATE{@SERVER, role:"用户明确授权操作的服务器", recommended:"全新 Debian 12 x86_64、systemd、root 登录、公网 80 与 443 端口可用"}
::STATE{@ENTRY, url:"https://fanqiang.guide/server/", installer:"https://fanqiang.guide/server/install.sh", api:"https://platform.deepseek.com"}
::STATE{@ASSISTANT, runtime:"PicoClaw v0.3.1", provider:"DeepSeek", model:"deepseek-flash", command:"huarun chat"}

::OBJECTIVE{id:server_setup|owner:@OWNER|trust:trusted|version:1|status:proposed}
  target: 在用户自己的 VPS 上安装华润网络服务与 PicoClaw 助手，将连接导入用户客户端，并按实际验证结果交付
  ACCEPT: 已安装网络服务和助手、服务端体检通过、用户实际客户端能访问预定白名单网站；不能把服务器体检当成手机连通证据
  DONE_WHEN: 所有本次要求的检查均有实际结果，用户拿到连接信息、对话入口和后续操作说明

::GENE{authorization|conf:confirmed|scope:global}
  T:仅在当前用户请求明确包含服务器安装或维护，且实际工具已连接目标服务器时执行；否则提供入口和步骤。
  T:这份公开工程书与知识 MCP 提供参考，不提供服务器访问权限，也不扩大已有授权。
  A:把下载书籍或连接 MCP 说成已经搭建完成⇒改报实际完成状态。
::GENE{private_input|conf:confirmed|scope:global}
  T:用户在自己的服务器终端隐藏输入 DeepSeek API Key，或使用已授权的本机秘密注入工具；密钥保留在目标服务器。
  T:不要把 SSH 密码、API Key、完整节点连接、私人日志发送到本 MCP、网页输入框、截图或公开报告。
  A:为了读取本书要求用户提供密钥⇒停止索取并直接读取公开内容。
::GENE{scope|conf:confirmed|scope:global}
  T:保留现有网站、网络设置与 SSH 访问。安装器发现已有 Nginx、Xray、华润安装或占用端口时会停止；复用现有安装的 huarun 管理命令。
  A:安装遇到冲突就卸载已有服务或重置服务器⇒说明具体冲突，获取缺少的目标选择后再继续。

::GENE{cost_claims|conf:confirmed|scope:global}
  T:10 元是建议的 API 起始余额，不是最低充值额或使用时长承诺；不得在没有长期费用与用量证据时声称实测终身够用。
  T:充值由用户自行决定和操作，不得自动替用户付款。

::MODULE{HOW}
  [STEP] 1 打开 https://platform.deepseek.com，充值 10 元，即可开始使用 AI 维护。VPS 自备，费用另计。创建自己的 API Key，留待服务器终端隐藏输入。
  [STEP] 2 通过用户现有的 SSH 方式连接其自己的全新 Debian 12 VPS。核对目标、系统、root 权限、端口和回退控制路径；本 MCP 不接收服务器密码或目标地址。
  [STEP] 3 读取 https://fanqiang.guide/server/ 的当前说明，在目标服务器执行 curl -fsSLo huarun-install.sh https://fanqiang.guide/server/install.sh && bash huarun-install.sh。让用户在隐藏提示中输入 Key；安装器先校验 Key 和模型，再部署网络服务和 PicoClaw。
  [STEP] 4 有域名时填写已指向该 VPS 的域名；无域名时直接回车，使用公网 IP 对应的 sslip.io 域名申请证书。选择页面样式并等待真实安装结果。失败时保留具体错误，不反复重装或清空配置。
  [STEP] 5 在用户的目标客户端本地导入安装器给出的完整 vmess 链接。需要再次查看时在服务器运行 huarun info。Windows、Linux、macOS 可用 v2rayN，Android 可用 v2rayNG，iPhone 或 iPad 可用 Shadowrocket；客户端安装与商店操作遵循用户已有授权。
  [STEP] 6 开启客户端并访问本次需要的白名单网站，例如 google.com 或 x.com。默认名单是服务器放行规则，名单外进入通道的请求被拒绝；不会自动给客户端配置名单外直连。
  [STEP] 7 以后 SSH 登录后运行 huarun chat，用中文描述问题。PicoClaw 在该 VPS 上调用 DeepSeek，并通过受限的 huarun 管理命令执行诊断与修复；这不是主站网页聊天终端。

::MODULE{REPAIR}
  [STEP] 1 用户说服务器或客户端连不上时，助手先执行 huarun doctor --json，区分本机服务、配置、证书、DNS、端口等检查结果。
  [STEP] 2 有可修的服务器故障时调用 huarun fix，再运行 huarun doctor --json 和 huarun status --json。失败则查看 huarun logs 50 并报告具体错误，不编造恢复。
  [STEP] 3 服务端检查通过后，让实际手机或电脑重新连接并访问目标网站。仍失败时继续收集目标客户端的必要现象，不能声称已验证不在控制范围内的客户端。
  [STEP] 4 按用户明确需求添加网站可用 huarun whitelist add example.com。清空或重置白名单、卸载和助手管理需用户在 SSH 终端自行确认；AI 命令闸不允许这些动作。

::RUBRIC{execution}
  [MUST] A1 当前目标是用户授权的 VPS，Key 未发送至知识 MCP 或网页。
  [MUST] A2 安装命令的退出状态与服务、配置、证书、助手存在性已检查；未完成的部分单独报告。
  [MUST] A3 实际客户端已导入连接并访问需要的网站；只有服务器检查时结果保持未完成客户端验证。
  [MUST] A4 后续用户知道 huarun info、huarun chat 的入口，修复结果对应工具证据。
  [MUST] A5 证据范围如实说明：当前安装器已有一次 Debian 12 x86_64、真实 Linux Xray 客户端与 PicoClaw/DeepSeek 修复验收；不代表真实手机、ARM 或全部发行版已验收。

::ILANG::v5.0::ENGINEERING_BOOK
