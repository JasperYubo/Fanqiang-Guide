# 翻墙指南 · 工具、路由器与 AI 配置参考

按设备找工具、核对官方资料，也可以把工程书交给自己的 AI，继续完成安装、配置与排错。

**310 条工具与知识记录 · MCP 2.1.0 · 两本设备工程书**

[打开官网](https://fanqiang.guide/) ｜ [研究成果](https://fanqiang.guide/research/) ｜ [完整目录](CATALOG.md) ｜ [版本动态](UPDATES.md) ｜ [每日免费节点与代理](free-proxies/)

## 你想做什么

| 现在的任务 | 从这里开始 |
| --- | --- |
| 为手机、电脑选择客户端 | [按设备浏览](#devices) · [全部工具](CATALOG.md) |
| 让自己的 AI 配置或排错 | [接入 MCP](#ai) · [设备工程书](#books) |
| 核对路由器型号、固件与插件 | [华硕与梅林](#merlin) · [OpenWrt](#openwrt) |
| 查看项目的新版本和来源 | [版本与项目动态](UPDATES.md) |
| 检查本机网络情况 | [本地网络诊断](https://fanqiang.guide/diagnostics/) |

<a id="start"></a>
## 新手从这里开始

1. **选设备**：找到对应的手机、电脑或路由器，查看工具用途与配置格式。
2. **查来源**：打开资料卡和官方页面，核对版本与设备要求；路由器还需确认完整型号、硬件版本和固件。
3. **继续操作**：按教程使用，或让已接入目标设备的 AI 阅读工程书，在你的授权范围内配置和验证。

<a id="ai"></a>
## 让 AI 使用这份知识库

远程 MCP 地址：**`https://fanqiang.guide/mcp`**。支持远程 MCP 的客户端可直接添加这个地址；使用 `mcpServers` JSON 配置的客户端可参考：

```json
{
  "mcpServers": {
    "fanqiang-guide": {
      "url": "https://fanqiang.guide/mcp"
    }
  }
}
```

`search` 查找条目，`get` 读取详情，`query` 按平台、协议、功能或路由器条件筛选。工程书通过 MCP 资源读取，完整接入方式见 [AI 入口](https://fanqiang.guide/ai/)。

<a id="books"></a>
### 设备工程书

| 工程书 | 用途 | MCP 资源 |
| --- | --- | --- |
| [设备配置 v2.1](apps/lookup/runtime/books/fanqiang-autosetup-v2.1.ilang.md) | 手机、电脑配置，手机共享与路由器流程入口 | `fanqiang://books/autosetup` |
| [梅林路由器 v1.0](apps/lookup/runtime/books/fanqiang-merlin-v1.0.ilang.md) | 梅林兼容固件、fancyss 选包、安装前检查与恢复流程 | `fanqiang://books/merlin` |

工程书提供流程，实际操作由你的 AI 通过目标设备工具执行；本站 MCP 提供只读资料。文档和接口验证、隔离 Linux 流程验证、真实手机与路由器测试的范围分别记录在[工程书元数据](https://fanqiang.guide/api/agent/books)中。

## 新手概念与教程

客户端提供操作界面，核心处理连接，协议约定通信方式。先分清这些概念，再选工具：

- [梯子、VPN 和代理有什么区别？](apps/site/public/guides/ladder-vpn-proxy.md)
- [机场、订阅和节点是什么？](apps/site/public/guides/airport-subscription-nodes.md)
- [路由器翻墙与科学上网怎么选？](apps/site/public/guides/router-guide.md)
- [工具与教程专题目录](https://fanqiang.guide/guides/index.html)

<a id="devices"></a>
## 按设备找工具

**[Windows](#windows) · [Android 安卓](#android) · [iPhone / iPad](#ios) · [macOS](#macos) · [Linux](#linux) · [华硕梅林](#merlin) · [OpenWrt](#openwrt)**

<a id="windows"></a>
## Windows 电脑翻墙工具

- [v2rayN](export/cards/v2rayn-v0.1-2026-09-11.md)：可配置 Xray、sing-box 等核心的图形客户端。
- [Clash Verge Rev](export/cards/clash-verge-rev-v0.1-2026-09-11.md)：内置 Mihomo 核心的桌面客户端。
- [FlClash](export/cards/flclash-v0.1-2026-09-11.md)：提供订阅导入与数据同步的跨平台工具。
- [Hiddify](export/cards/hiddify-v0.1-2026-09-11.md)：基于 sing-box，支持多种配置格式导入。
- [Karing](export/cards/karing-v0.1-2026-09-11.md)：支持多种订阅格式、规则配置与配置同步。

<a id="android"></a>
## Android 安卓翻墙工具

- [v2rayNG](export/cards/v2rayng-v0.1-2026-09-11.md)：支持 Xray 与 V2Fly 核心的安卓客户端。
- [Clash Meta for Android](export/cards/clash-meta-for-android-v0.1-2026-09-11.md)：Clash.Meta 的安卓图形客户端。
- [FlClash](export/cards/flclash-v0.1-2026-09-11.md)：使用 Clash.Meta 核心，支持订阅导入。
- [Hiddify](export/cards/hiddify-v0.1-2026-09-11.md)：使用 sing-box 核心，支持配置订阅。
- [Karing](export/cards/karing-v0.1-2026-09-11.md)：可在多种设备上使用的代理工具。

<a id="ios"></a>
## iPhone / iPad 翻墙工具

- [Shadowrocket 小火箭](export/cards/shadowrocket-v0.1-2026-09-11.md)：支持规则分流、DNS 设置和请求记录。
- [Quantumult X](export/cards/quantumult-x-v0.1-2026-09-11.md)：提供规则分流、请求重写与网络调试功能。
- [Surge](export/cards/surge-v0.1-2026-09-11.md)：包含代理分流、DNS 控制与网络调试的工具箱。
- [Streisand](export/cards/streisand-v0.1-2026-09-11.md)：支持多协议接入、规则配置与自定义 DNS。
- [Karing](export/cards/karing-v0.1-2026-09-11.md)：支持 iOS 的跨平台代理工具。

<a id="macos"></a>
## macOS 苹果电脑翻墙工具

[Clash Verge Rev](export/cards/clash-verge-rev-v0.1-2026-09-11.md) · [v2rayN](export/cards/v2rayn-v0.1-2026-09-11.md) · [Surge](export/cards/surge-v0.1-2026-09-11.md) · [FlClash](export/cards/flclash-v0.1-2026-09-11.md) · [Hiddify](export/cards/hiddify-v0.1-2026-09-11.md)

<a id="linux"></a>
## Linux 翻墙工具

[v2rayN](export/cards/v2rayn-v0.1-2026-09-11.md) · [Clash Verge Rev](export/cards/clash-verge-rev-v0.1-2026-09-11.md) · [FlClash](export/cards/flclash-v0.1-2026-09-11.md) · [Hiddify](export/cards/hiddify-v0.1-2026-09-11.md) · [Karing](export/cards/karing-v0.1-2026-09-11.md)

<a id="merlin"></a>
## 华硕路由器与梅林固件

先看[华硕与梅林生态说明](knowledge/merlin-guide-v0.1-2026-09-11.md)，再按完整型号和硬件版本查阅[历史固件支持声明](knowledge/merlin-model-matrix-v0.1-2026-09-11.md)。当前选包与安装前检查见[梅林工程书](apps/lookup/runtime/books/fanqiang-merlin-v1.0.ilang.md)和[兼容资料](data/router-compatibility.json)。

- [Asuswrt-Merlin 原版梅林](export/cards/asuswrt-merlin-v0.1-2026-09-11.md)：在 ASUSWRT 基础上扩展功能的第三方固件。
- [GNUton 梅林分支](export/cards/asuswrt-merlin-gnuton-v0.1-2026-09-11.md)：扩展华硕机型支持范围的独立分支。
- [KoolCenter 梅林改版](export/cards/koolcenter-merlin-mod-v0.1-2026-09-11.md)：加入软件中心及配套组件的梅林改版固件。
- [fancyss](export/cards/fancyss-v0.1-2026-09-11.md)：面向带软件中心的 ASUSWRT / 梅林衍生固件的代理插件。
- [MerlinClash](export/cards/merlinclash-v0.1-2026-09-11.md)：用于华硕官改、梅改固件的 Mihomo 代理插件。
- [Entware](export/cards/entware-v0.1-2026-09-11.md) 与 [amtm](export/cards/amtm-v0.1-2026-09-11.md)：了解路由器软件包和扩展脚本的管理方式。

<a id="openwrt"></a>
## OpenWrt 与路由器插件

- [OpenWrt](export/cards/openwrt-v0.1-2026-09-11.md)：了解固件与软件包生态。
- [OpenClash](export/cards/openclash-v0.1-2026-09-11.md)：在 OpenWrt 中配置和管理 Mihomo 代理。
- [PassWall2](export/cards/passwall2-v0.1-2026-09-11.md)：多协议代理、DNS 与流量策略管理。
- [Nikki](export/cards/nikki-v0.1-2026-09-11.md)：在 OpenWrt 上管理 Mihomo 透明代理。
- [HomeProxy](export/cards/homeproxy-v0.1-2026-09-11.md)：面向 ImmortalWrt 的 sing-box 配置平台。
- [更多路由器固件](CATALOG.md#router-firmware) · [更多路由器插件](CATALOG.md#router-plugins)

## 代理核心、协议与网络知识

- **代理核心**：[Mihomo](export/cards/mihomo-v0.1-2026-09-11.md) · [sing-box](export/cards/sing-box-v0.1-2026-09-11.md) · [Xray-core](export/cards/xray-core-v0.1-2026-09-11.md) · [Hysteria](export/cards/hysteria-v0.1-2026-09-11.md)
- **基础概念**：[TUN](export/cards/concept-tun-v0.1-2026-09-11.md) · [FakeIP](export/cards/concept-fakeip-v0.1-2026-09-11.md) · [规则集](export/cards/concept-ruleset-v0.1-2026-09-11.md)
- **继续查找**：[代理协议](CATALOG.md#protocols) · [DNS 工具](CATALOG.md#dns) · [分流规则](CATALOG.md#rules)

<a id="official-docs"></a>
## 官方教程与技术文档

- **[Xray 官方中文文档](https://xtls.github.io/)**：快速入门、配置指南、入门与进阶技巧，以及 VLESS、REALITY 等技术资料。
- **[sing-box 官方文档](https://sing-box.sagernet.org/)**：客户端、服务端、DNS、路由和配置迁移说明，适合查配置与排错；站内可切换简体中文。

[查看全部 310 个工具与知识条目 →](CATALOG.md)

<a id="research"></a>
## 研究成果与引用

网站的核心方法整理为一篇系统技术报告和三篇专题技术说明。每篇都有独立正文、参考文献与 DOI；[研究入口](https://fanqiang.guide/research/)提供全文与下载。

| 出版物 | 研究范围 | DOI |
| --- | --- | --- |
| [华润（Fanqiang Guide）：面向 AI 设备配置的知识组织、执行协议与诊断体系](https://fanqiang.guide/research/fanqiang-guide-system/) | 系统模型、证据组织与复现范围 | [10.5281/zenodo.23961021](https://doi.org/10.5281/zenodo.23961021) |
| [面向用户自主 AI 的设备配置协议：目标绑定、局部修复与证据验收](https://fanqiang.guide/research/device-setup-protocol/) | 设备识别、局部修复与验收 | [10.5281/zenodo.23961041](https://doi.org/10.5281/zenodo.23961041) |
| [基于来源约束与未知状态的梅林路由器插件包匹配方法](https://fanqiang.guide/research/router-package-matching/) | 型号、固件分支及 full/lite 匹配 | [10.5281/zenodo.23961043](https://doi.org/10.5281/zenodo.23961043) |
| [本地网络诊断的有限测量与主动提交协议](https://fanqiang.guide/research/local-diagnostics-consent/) | 有限测量、脱敏预览与主动提交 | [10.5281/zenodo.23961045](https://doi.org/10.5281/zenodo.23961045) |

四篇 1.0 版对应 2026-11-04 的方法整理，基础实现固定为 7bfc3e01e3fcea3866ac1b57e69f5461a2b1b250。接口检查、隔离 Linux 流程与真实硬件验收的范围在各篇中分别说明。

整体方法优先引用主报告；具体设备流程、选包或诊断方法引用对应专题，并注明使用的代码或工程书版本。GitHub 引用入口由 [CITATION.cff](CITATION.cff) 提供；出版物元数据见 [research/publications.json](research/publications.json)，维护规则见[引用与版本说明](developer/CITATION.md)。

## 资料如何更新

[版本动态](UPDATES.md)记录上游仓库与正式 Release 的自动观察结果；[来源时效接口](https://fanqiang.guide/api/agent/freshness)区分当前、过期、未知和未监测状态。资料卡保留各自的人工核对日期，版本检查不会把旧教程变成新一轮实测。

当前有 **310 条知识记录**、**56 行路由器兼容匹配资料**；旧型号表另保留 **58 条固件支持声明**。这三个集合用途不同。兼容资料来自发布方说明与离线包检查，真实手机和路由器操作仍需按工程书在目标设备上验证。

免费代理页面自动整理来源与格式统计。[路由器上游观察](developer/ROUTER_UPSTREAM_WATCH.md)按日检查 fancyss 与已记录的 KoolCenter 来源变化，生成待人工复核报告，兼容矩阵仍由审核后更新。自动化不安装上游程序、不重写教程，也不把来源可访问或格式正确当作节点连通性结果。

[开发与维护索引](developer/README.md) · [资料重建方法](tools/README.md) · [自动更新说明](.github/maintenance-v0.1-2026-09-12.md)
