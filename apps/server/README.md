# 华润服务器助手

[从华润主站开始安装](https://fanqiang.guide/server/)

把自己的 VPS 配成可用的网络通道，再给它装上一位能用中文排错的 AI 助手。

你买好了一台海外服务器，想在手机或电脑上稳定使用跨境业务平台：先准备 DeepSeek Key，再连接服务器运行安装命令，最后把生成的连接链接导入客户端。以后连不上，直接对助手说“帮我看看哪里出了问题”。

## 1. 给 DeepSeek 充值 10 元，创建 Key

打开 [DeepSeek 开放平台](https://platform.deepseek.com)，登录后充值 **10 元**，再在 API Keys 页面创建自己的 API Key。

充值 10 元，即可开始使用 AI 维护。VPS 自备，费用另计。助手使用你的 Key，默认模型为 `deepseek-flash`。

先保管好 Key，稍后在自己的服务器终端里粘贴。华润网页不收集 Key，也不用把它发进聊天。

## 2. 连接自己的服务器

准备一台**全新的 Debian 12 x64 VPS**，可以使用 root 登录，公网 80、443 端口可用。服务商控制台若有防火墙或安全组，也要放行这两个端口。

在电脑终端中连接，把示例 IP 替换成你的服务器公网 IP：

```bash
ssh root@203.0.113.10
```

按终端提示完成服务器登录。已有网站或其他网络服务的机器，请先另备一台空白 VPS；安装器会在发现冲突时停止。

## 3. 安装网络服务和 AI 助手

在刚连上的服务器里执行：

```bash
curl -fsSLo huarun-install.sh https://fanqiang.guide/server/install.sh && bash huarun-install.sh
```

如果系统提示找不到 `curl`，先安装下载工具，再执行上面的命令：

```bash
apt-get update && apt-get install -y curl ca-certificates
```

按提示粘贴 DeepSeek Key，输入时不会回显。安装器先检查 Key，再安装网络服务和内置的 **PicoClaw AI 助手**。

有域名就填已经解析到这台服务器的域名；没有域名可以直接回车，安装器会使用公网 IP 对应的 `sslip.io` 域名申请 HTTPS 证书。选择首页样式后，等待终端显示安装结果。

安装完成会给出一整行 `vmess://` 连接链接。证书续期已由服务器定时处理。

## 4. 导入手机或电脑，打开连接

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

## 一次启用，以后自动更新

新安装默认开启自动更新；VPS 每 6 小时检查正式发布的新版本，保留原节点配置、白名单、Key 和聊天记忆。旧版只需 SSH 一次启用，以后自动维护。

旧版 1.0 / 1.1 没有自动更新程序，需要你 SSH 登录原来的 VPS，执行一次下面的命令；新安装已经默认开启，无需重复执行：

```bash
curl -fsSLo huarun-install.sh https://fanqiang.guide/server/install.sh && bash huarun-install.sh --upgrade-assistant
```

这会更新内置助手和 `huarun` 管理命令，并启用 VPS 本机定时更新。保留原节点配置、连接信息、白名单、DeepSeek Key 和聊天记忆，不重装网络，也不重启 Xray 或 Nginx。

更新只采用 GitHub 已正式发布且主站与 .io 页面一致的版本。每 6 小时检查一次，开机 10 分钟后检查，另有最多 30 分钟随机错峰。升级前先备份，失败则回滚；正在聊天或运行管理操作时延期。

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
huarun chat
```

然后用中文提出需求：

- “手机连不上了，帮我检查并修复。”
- “把连接信息给我，告诉我怎么导入。”
- “把 example.com 加进白名单。”
- “证书还剩多少天？”

每轮先查华润 MCP 的文档和排障资料；资料不足再用 DeepSeek 搜索；修复后自动复查服务状态。它会结合服务器上的检查、修复和查询结果，给出所用资料来源和实际结果。服务端检查正常后，仍需用你的手机或电脑打开目标网站，确认本地连接也已恢复。

如果助手暂时无法对话，先检查 DeepSeek 余额和 Key；网络通道与 AI 对话分别运行，仍可使用终端管理命令：

```bash
huarun status --json
huarun doctor --json
huarun fix
```

安装中途失败时保留终端报错，先检查报错所指的域名、端口、下载连接或 API 问题。不要清空现有配置后反复安装。

## 与常用的 AI 一起安装

在支持远程 MCP 的 AI 客户端中连接 https://fanqiang.guide/mcp，获取同一套服务器安装说明。公共 MCP 只提供资料，操作由你授权的 AI 在自己的 VPS 上完成。

- 安装工具：get_server_setup
- 安装提示：setup_server
- 工程书资源：fanqiang://books/server
- [服务器助手工程书](https://fanqiang.guide/ai/books/fanqiang-server-v1.2.ilang.md)
- [安装脚本](https://fanqiang.guide/server/install.sh)

搜索和对话均使用你自己的 DeepSeek API Key，按官方实际用量计费。

当前内置 PicoClaw v0.3.1，默认使用 DeepSeek 的 deepseek-flash 模型。
