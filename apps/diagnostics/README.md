# Fanqiang 本地网络诊断 v0.1.0

本工具先在本机测量，再由本人决定是否提交结果。可直接打开本地网页，也可接入支持 stdio MCP 的 AI 客户端。不会自动修改代理、DNS、路由、AI 配置或安装后台服务。

发布入口：https://fanqiang.guide/diagnostics/  
报告接收地址：https://fanqiang.guide/diagnostics-api

## Windows x64：解压即用

1. 下载 fanqiang-diagnostics-0.1.0-windows-x64.zip，完整解压。
2. 双击“开始诊断.cmd”，使用随包 Node.js 打开本地页面。
3. 阅读固定目标与预算，点击开始。下载测速默认关闭。
4. 查看报告；只有在页面预览后点击“提交这份报告”，才上传到 Fanqiang。
5. 保留运行窗口；关闭窗口或 Ctrl+C 结束本次本地进程。

不要在 ZIP 内只打开单个脚本。支持含空格的目录；移动目录后需重新生成 MCP 配置。

Windows 包在 Linux 上完成打包、许可证与文件校验，尚未在 Windows 原生运行测试。本次运行时包仅覆盖 Windows x64、Linux x64，不含 ARM 或 macOS。

## Linux x64：便携运行或安装

完整解压 fanqiang-diagnostics-0.1.0-linux-x64.tar.gz，在目录中执行：

    ./开始诊断.sh

使用随包 Node.js，无需另装 npm。系统需能运行官方 Node.js 24 的 Linux x64 二进制。没有桌面浏览器时，终端会显示本地地址；应在运行工具的同一台设备打开，不要公开或通过公网转发该地址。

可选安装：

    ./安装到当前用户.sh

安装器只写当前用户的 ~/.local/share/fanqiang-diagnostics，不需要 sudo，不修改 PATH、服务或 AI 全局配置。程序放入 releases/，现有 session-* 报告和回执会保留。安装结束后显示稳定启动脚本的完整路径。便携运行无需安装。

高级安装可使用 ./安装到当前用户.sh --prefix /绝对/程序目录；这只改变程序位置，报告仍使用默认本地数据目录。\n\n关闭终端或 Ctrl+C 结束进程。卸载前，先在页面处理需要删除的远端报告，再删除程序目录。升级不应清空整个数据目录，否则会失去回执与删除凭证。

## 接入 MCP

运行“生成MCP配置.cmd”或“生成MCP配置.sh”。脚本在自身目录写出 mcp-config.json，使用当前 Node.js 与 client.mjs 的绝对路径。

手动把 mcpServers 中的 fanqiang-diagnostics 条目合并到 AI 客户端 MCP 设置，不要覆盖其他配置。工具不会自动修改设置；移动或安装到新目录后请重新生成。

四个工具均不接受额外参数：

| 工具 | 功能 |
| --- | --- |
| diagnostics_open | 返回本地页面地址，等本人点击开始；不自动测试或提交。 |
| diagnostics_status | 读取测量进度。 |
| diagnostics_preview | 把结构化报告返回当前 AI 客户端，不包含日志全文；不提交到 Fanqiang。 |
| diagnostics_stop | 停止测量，保留已有样本，不上传。 |

没有 MCP 上传工具。Fanqiang 提交只能由本人在本地浏览器预览并点击确认。调用 diagnostics_preview 后，结构化报告会进入当前 AI 客户端上下文，其后续处理取决于该客户端。

已有 Node.js >=20.19 环境可使用 npm 包；它包含自包含 client.mjs，不含运行时，也没有需从 registry 下载的运行依赖。把 npm.tgz 放在当前目录后，可离线安装到独立目录：

    npm install --prefix ./fanqiang-diagnostics-app ./fanqiang-diagnostics-0.1.0-npm.tgz --ignore-scripts --offline --no-audit --no-fund
    node "./fanqiang-diagnostics-app/node_modules/@fanqiang/diagnostics-mcp/dist/client.mjs" --print-config
    node "./fanqiang-diagnostics-app/node_modules/@fanqiang/diagnostics-mcp/dist/client.mjs" --web --open

这不修改全局 npm 安装或 AI 配置。也可在包目录使用开发者入口：

    node dist/client.mjs --web --open
    node dist/client.mjs --print-config
    node dist/client.mjs --stdio

--lab 用于明确标记 Linux 实验环境，不能把服务器结果称为用户设备实测。

## 测量与预算

目标固定为 fanqiang.guide 的诊断接口，不接受任意网址、不跟随重定向。DNS、TCP、TLS、HTTP 每种最多 3 个样本；未开始的阶段保留空数组。可选下载最多 1 个样本。

每次最多接收 10 MiB HTTP 响应体，包含小型 HTTP 探测；同一本地会话最多 20 MiB。下载默认关闭。总截止时间 15 秒；达到上限或停止时取消解析与连接。操作系统调度可能造成毫秒级延迟。预算是应用接收的响应体，不含 DNS/TCP/TLS 协议开销。

失败和未完成结果不是零速度；中位数只计算成功样本。TCP 失败比例是本次连接尝试结果，取消不计入分母，不是 ICMP 丢包率。

## 隐私、保存、删除与恢复

上传 schema 0.1 只允许固定枚举、时间、样本、汇总和预算字段，不接受任意文字、IP、网址、节点配置、设备名称、序列号、用户名或日志全文。

日志脱敏仅供本地预览，支持常见 IP、MAC、邮箱、URL、订阅、凭据及文件路径。脱敏是辅助处理；原始与脱敏后的日志全文均不进入报告、不通过 MCP 返回 AI。报告最多记录识别到的信息类别。正常网络连接仍会传递连接信息。

本地数据默认位于当前用户主目录中的 .local/share/fanqiang-diagnostics（Windows 对应 .local\share\fanqiang-diagnostics）。每次会话使用 session-* 子目录。结构化报告、提交状态和回执本地保存；删除令牌留在回执文件内，不展示给 AI。

主动提交的报告服务端最长保留 30 天，回执显示实际到期时间，过期记录自动清理。报告不是公开案例；回执只确认格式和接收状态，不证明报告真实、测量准确或网络服务可用。

- “删除远端报告”使用本地回执中的凭证删除本次提交。
- 远端删除成功后，再“删除本地数据”，清除报告和回执。
- 提交状态不明确时保留本地状态，供同一报告重试；不要先清理回执。
- 重启后可恢复最近可恢复的提交或待确认提交，再重试或删除；恢复不会自动测速或上传。
- 恢复不包含日志全文。关闭网页不等于删除已提交报告。

## 适用范围

本版使用 OS 直接 socket，不自动使用系统显式 HTTP 代理、HTTP_PROXY、HTTPS_PROXY 或 SOCKS。已经启用的 TUN/VPN/透明路由仍可能影响连接。因此结果不能证明某个应用的 HTTP/SOCKS 代理配置生效。

DNS 使用系统配置 DNS 服务器查询 A/AAAA，不测浏览器 DoH、代理内部 DNS 或 hosts/NSS。TLS 包含 TCP 新建连接，HTTP 也包含连接时间。所有连接保留证书验证，解析地址固定到连接，并拒绝私网、metadata、映射及部分特殊用途地址。

固定站点的小样本不代表全部网站、地区、运营商、设备或长期表现；有限下载不是宽带套餐测速认证。本版没有应用内抓包、节点探测或实机兼容认证。

传输 schema 比完整编辑证据模板精简，不传截图、自由文本案例、原始环境或日志附件。真实截图与设备实验需另行处理，不能由此报告代替。

## 校验与许可证

下载目录提供 SHA256SUMS.txt。便携包内 PACKAGING.json 记录文件摘要与运行时原始归档摘要。

应用采用仓库 MIT 许可证，见 LICENSE.txt。随包 Node.js 24.18.1 的原始 LICENSE 在 licenses/Node-LICENSE.txt；SDK 依赖许可证参考在 licenses/THIRD_PARTY_NOTICES.txt。请保留“打包法律声明.txt”和各上游声明。

源代码：https://github.com/JasperYubo/Fanqiang-Guide/tree/main/apps/diagnostics
