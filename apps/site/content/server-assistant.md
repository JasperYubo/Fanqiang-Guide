# 华润服务器助手

[从华润主站开始安装]({{SERVER_ENTRY_URL}})

把自己的 VPS 配成可用的网络通道，再给它装上一位能用中文排错的 AI 助手。

你买好了一台海外服务器，想在手机或电脑上稳定使用跨境业务平台：先准备自己的 Cloudflare 域名与 {{PROVIDER}} Key，再连接服务器运行安装命令，把固定域名连接导入客户端。IP 改变后由 VPS 同步解析，证书和故障通知也在服务器上维护。以后连不上，直接对助手说“帮我看看哪里出了问题”。

## 1. 准备 Cloudflare 域名与全权限账户令牌

将自己的域名接入 [Cloudflare](https://dash.cloudflare.com)，确认 DNS 区域已激活。进入该账户的 **Manage account → Account API tokens（账户 API 令牌）→ Create Token**，选择 **Full account and zone access**，创建并保管完整令牌。

准备要使用的完整域名，例如 `node.example.com`。安装时在 VPS 终端隐藏输入令牌，由本机工具自动识别 Account ID 与 Zone ID，并配置对应记录与 TLS；网页和 AI 聊天不需要粘贴令牌。

## 2. 给 {{PROVIDER}} 充值 {{PRICE_AMOUNT}} 元，创建 Key

打开 [{{PROVIDER}} 开放平台]({{API_URL}})，登录后充值 **{{PRICE_AMOUNT}} 元**，再在 API Keys 页面创建自己的 API Key。

{{PRICE_SENTENCE}}助手使用你的 Key，默认模型为 `{{MODEL}}`。

先保管好 Key，稍后在自己的服务器终端里粘贴。华润网页不收集 Key，也不用把它发进聊天。

## 3. 连接自己的服务器

准备一台**{{OS_LABEL}}**，可以使用 root 登录，公网 80、443 端口可用。服务商控制台若有防火墙或安全组，也要放行这两个端口。

在电脑终端中连接，把示例 IP 替换成你的服务器公网 IP：

```bash
ssh root@203.0.113.10
```

按终端提示完成服务器登录。已有网站或其他网络服务的机器，请先另备一台空白 VPS；安装器会在发现冲突时停止。

## 4. 安装网络服务和 AI 助手

在刚连上的服务器里执行：

```bash
{{INSTALL_COMMAND}}
```

如果系统提示找不到 `curl`，先安装下载工具，再执行上面的命令：

```bash
apt-get update && apt-get install -y curl ca-certificates
```

按提示粘贴 {{PROVIDER}} Key，输入时不会回显。安装器先检查 Key，再安装网络服务和内置的 **{{RUNTIME}} AI 助手**。

按提示输入 Cloudflare 的 Full account and zone access 账户令牌与自己的固定域名，安装器自动识别并验证 Account ID 与 Zone ID。安装器用 DNS-01 申请有效 TLS 证书并配置续期。选择首页样式后，等待终端显示安装结果。

安装完成会给出一整行 `vmess://` 连接链接。证书续期已由服务器定时处理。

## 5. 导入手机或电脑，打开连接

在服务器运行下面的命令，可以重新查看连接链接：

```bash
huarun info
```

复制完整的 `vmess://` 链接，在自己的客户端选择“从剪贴板导入”，选中该节点并开启连接。

| 设备 | 可用客户端 |
| --- | --- |
| Windows / Linux / macOS | v2rayN |
| Android | v2rayNG |
| iPhone / iPad | Shadowrocket |

打开白名单里的业务平台，例如 `x.com` 或 `google.com`，检查实际访问是否正常。默认允许 383 个业务根域名及其子域名；进入通道的名单外请求会被拒绝。需要添加网站，可以告诉助手。

## 固定域名、动态 IP 与故障通知

{{NETWORK_SENTENCE}}

{{NETWORK_PROXY_SENTENCE}}

在自己的 SSH 终端配置或查看：

```bash
huarun network setup
huarun network status
huarun network check
huarun network notify-test
```

通知使用 Telegram；在 setup 中输入自己的 Bot Token 与 Chat ID，发送测试并确认实际收件。未配置会显示 `not_configured`；发送失败会保留队列重试，不会显示成已送达。

证书有效期用 `huarun doctor --json` 查看，完整节点的 TLS 和访问通路用 `huarun egress probe` 验证。`network status` 返回网络维护状态，不包含证书检查结果。

动态 IP 同步读取 VPS 的真实入站地址；Cloudflare CDN 地址或链式出口 IP 不会被当作源站。DNS 同步后仍需等待客户端缓存刷新，并复查实际连接。

自动换 IP 不限制 VPS 厂商。比如你使用一家没有现成适配器的服务商，新安装在 `huarun network setup` 选择自动发现；已有用户只需运行 `huarun network provider-setup`，补充厂商名称、可选官网、实例和已有 API 凭据，保留原 Cloudflare 令牌、域名与节点，不必重装。保存后，Agent 会先查华润 MCP，再查并读取厂商官方文档。发现可用的换 IP API 后，自动生成适配、校验请求与官方依据，并只读核对实例和当前地址，验证通过后启用，不需要你自己写接口代码。

可以直接告诉助手：“检查这家 VPS 的官方换 IP API，能对接就接好并验证。”也可在 SSH 终端查看过程和结果：

```bash
huarun network provider-setup
huarun network provider-discover
huarun network provider-status
```

`network check` 和 Linux 定时维护也会自动执行发现，复用已经验证的适配结果。确实没有 API 时通知你到厂商面板处理；文档暂时不可访问、缺少凭据、权限或预算不足，以及签名方式暂不支持，会分别说明缺少的条件，不会把它们当作“厂商没有 API”。

以下是可直接复用的现成适配器，不是厂商支持名单的上限：

| 现成适配器 | 地址与条件 |
| --- | --- |
| DigitalOcean | Reserved IPv4；更换时需授权短暂解绑旧地址 |
| Hetzner | Floating IPv4；保留原主地址与旧绑定 |
| Vultr | Cloud Compute Reserved IPv4；Bare Metal 需外部控制器 |
| AWS | 目标已绑定 Elastic IP；普通自动分配公网 IP 的停启恢复需外部控制器 |

实际更换仍须本机已保存自动更换和适用的分配、中断授权，费用与次数符合预算，并达到独立地区探针的故障条件。API 受理之后要验证新地址、同步并读回 DNS，再复查通路；失败保留恢复事务或回滚，不会重复申请未知结果的付费地址。预算是适配器资源估算，不是全账户账单硬限。真实云 API 换 IP 的验证范围见[本版工程书元数据](https://fanqiang.guide/api/agent/books/server)，与隔离测试分别记录。单点超时不会直接判定“IP 被墙”。

## 接入已有家宽等出口代理

{{EGRESS_SENTENCE}}

先准备你自己的出口代理服务，在 SSH 终端保存带名称的配置：

```bash
huarun egress setup home
huarun egress status
huarun egress probe
```

上面的命令会保存名为 `home` 的出口；完成后，可以对助手说“切换到 home 出口，再检查出口 IP”。也可以在终端运行：

```bash
huarun egress use home
```

这里只对接你已准备的 SOCKS5 或 HTTP CONNECT **TCP** 出口，不代购家宽，也不改变 VPS 的入站域名。原白名单继续生效；选中出口失效时不悄悄改为直连。需要恢复直连时，明确告诉助手，或运行 `huarun egress direct`。

## 一次启用，以后自动更新

{{AUTOMATIC_UPDATE_SENTENCE}}

旧版 1.0 / 1.1 没有自动更新程序，需要你 SSH 登录原来的 VPS，执行一次下面的命令；新安装已经默认开启，无需重复执行：

```bash
{{UPGRADE_COMMAND}}
```

这会更新内置助手和 `huarun` 管理命令，并启用 VPS 本机定时更新。保留原节点配置、连接信息、白名单、DeepSeek Key 和聊天记忆，不重装网络，也不重启 Xray 或 Nginx。

更新只采用 GitHub 已正式发布且主站与 .io 页面一致的版本。每 6 小时检查一次，开机 10 分钟后检查，另有最多 30 分钟随机错峰。升级前先备份，失败则回滚；正在聊天或运行管理操作时延期。

已有用户接入 Cloudflare 固定域名时，单独运行 `huarun network setup`。程序先申请新证书，再迁移域名并复查，失败恢复原配置；UUID、WebSocket 路径、白名单和 DeepSeek Key 保留。成功后用 `huarun info` 获取新域名连接，重新导入客户端。普通自动升级不会替你改域名。

查看当前版本、定时器和最近检查结果：

```bash
huarun auto-update status
```

需要立即检查、暂停或恢复时，由管理员在 SSH 终端操作：

```bash
huarun auto-update check
huarun auto-update disable
huarun auto-update enable
```

内置 Agent 可以查询更新状态，不能关闭或改动自动更新。旧版没有中央控制通道，网页不能直接替它开启；完成这一次迁移后，后续更新由 VPS 自己处理，不依赖你的电脑开机。

## 有问题，直接和助手说

以后 SSH 登录这台服务器，运行：

```bash
{{CHAT_COMMAND}}
```

然后用中文提出需求：

- “手机连不上了，帮我检查并修复。”
- “把连接信息给我，告诉我怎么导入。”
- “把 example.com 加进白名单。”
- “证书还剩多少天？”
- “检查固定域名解析和故障通知是否正常。”
- “查这家 VPS 的官方换 IP API，能对接就接好并验证。”
- “切换到已经配置的 home 出口，并复查出口 IP。”

{{KNOWLEDGE_SENTENCE}}它会结合服务器上的检查、修复和查询结果，给出所用资料来源和实际结果。服务端检查正常后，仍需用你的手机或电脑打开目标网站，确认本地连接也已恢复。

如果助手暂时无法对话，先检查 {{PROVIDER}} 余额和 Key；网络通道与 AI 对话分别运行，仍可使用终端管理命令：

```bash
huarun status --json
huarun doctor --json
huarun fix
```

安装中途失败时保留终端报错，先检查报错所指的域名、端口、下载连接或 API 问题。不要清空现有配置后反复安装。

## 与常用的 AI 一起安装

在支持远程 MCP 的 AI 客户端中连接 {{MCP_URL}}，获取同一套服务器安装说明。公共 MCP 只提供资料，操作由你授权的 AI 在自己的 VPS 上完成。

- 安装工具：{{SERVER_TOOL}}
- 安装提示：{{SERVER_PROMPT}}
- 工程书资源：{{SERVER_RESOURCE}}
- [服务器助手工程书]({{SERVER_BOOK_URL}})
- [安装脚本]({{INSTALLER_URL}})

搜索和对话均使用你自己的 DeepSeek API Key，按官方实际用量计费。

当前内置 {{RUNTIME}} v{{RUNTIME_VERSION}}，默认使用 {{PROVIDER}} 的 {{MODEL}} 模型。
