# 翻墙指南｜科学上网工具、华硕梅林与 OpenWrt 资料库

先找到适合你设备的工具。从手机、电脑到路由器，按设备了解科学上网工具，把客户端、代理核心和固件的关系理清楚。

- 官网：[fanqiang.guide](https://fanqiang.guide/)
- [完整工具与知识目录：310 个条目，20 个分类](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/CATALOG.md)
- [软件版本与项目动态](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/UPDATES.md)
- [GitHub 公开知识库](https://github.com/JasperYubo/Fanqiang-Guide)

## 第一次来，从这里开始

1. **确认自己的设备。** 手机、电脑看操作系统；路由器先看完整型号和固件。
2. **了解工具负责什么。** 客户端提供界面，核心处理连接，协议约定通信方式。
3. **沿着来源继续阅读。** 每个资料条目提供中文介绍，帮助你找到对应项目与说明。

[先读基础概念](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/CATALOG.md#concepts)

## 按设备查找

先选系统，再看工具介绍与支持范围。

| 设备与系统 | 资料入口 |
| --- | --- |
| Windows 电脑 | [Windows 客户端](https://github.com/JasperYubo/Fanqiang-Guide#windows) |
| Android 安卓手机与平板 | [Android 客户端](https://github.com/JasperYubo/Fanqiang-Guide#android) |
| iPhone / iPad | [Apple 移动设备工具](https://github.com/JasperYubo/Fanqiang-Guide#ios) |
| macOS 苹果电脑 | [macOS 客户端](https://github.com/JasperYubo/Fanqiang-Guide#macos) |
| Linux | [Linux 桌面与命令行工具](https://github.com/JasperYubo/Fanqiang-Guide#linux) |
| 华硕梅林 | [型号、固件与插件资料](https://github.com/JasperYubo/Fanqiang-Guide#merlin) |
| OpenWrt | [固件与插件生态](https://github.com/JasperYubo/Fanqiang-Guide#openwrt) |

## 从这些工具开始了解

| 工具 | 用途 | 平台 |
| --- | --- | --- |
| [v2rayN](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/export/cards/v2rayn-v0.1-2026-09-11.md) | 可配置 Xray、sing-box 等核心的图形客户端 | Windows、macOS、Linux |
| [v2rayNG](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/export/cards/v2rayng-v0.1-2026-09-11.md) | 支持 Xray 与 V2Fly 核心的 Android 客户端 | Android |
| [Shadowrocket 小火箭](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/export/cards/shadowrocket-v0.1-2026-09-11.md) | 支持规则分流、DNS 设置和请求记录的代理工具 | iOS、iPadOS、macOS 等 Apple 平台 |
| [Clash Verge Rev](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/export/cards/clash-verge-rev-v0.1-2026-09-11.md) | 内置 Mihomo 核心，提供桌面图形界面与配置管理 | Windows、macOS、Linux |
| [Hiddify](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/export/cards/hiddify-v0.1-2026-09-11.md) | 基于 sing-box，支持配置订阅与多种配置格式导入 | Android、iOS、Windows、macOS、Linux |
| [Karing](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/export/cards/karing-v0.1-2026-09-11.md) | 支持多种订阅格式、规则配置和多设备配置同步 | Android、iOS、桌面系统、tvOS |

[查看全部客户端](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/CATALOG.md#clients)

## 华硕梅林：先分清固件与插件

原版 Merlin、GNUton、软件中心、fancyss、MerlinClash，名称相近，负责的事情不同。先理清关系，再对照自己的路由器型号。

- [阅读梅林入门说明](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/knowledge/merlin-guide-v0.1-2026-09-11.md)
- [我的路由器在支持清单里吗？](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/knowledge/merlin-model-matrix-v0.1-2026-09-11.md)：按完整型号、硬件版本和固件项目查阅。
- [了解不同固件项目](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/CATALOG.md#router-firmware)：区分 ASUSWRT、原版梅林、GNUton 与改版固件。
- [继续查找路由器插件](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/CATALOG.md#router-plugins)：了解插件用途与对应固件生态。

支持清单来自项目说明；固件与插件的兼容范围需分别核对。

## 工具之外，也把基础理清楚

- [代理核心](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/CATALOG.md#cores)：Mihomo、sing-box、Xray 与客户端是什么关系？
- [协议与连接](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/CATALOG.md#protocols)：从工具介绍中的协议名称，找到对应资料。
- [DNS 与分流](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/CATALOG.md#dns)：了解 DNS 工具，再查阅规则集和基础概念。

## 每日免费节点与代理资料

公开订阅与 HTTP / SOCKS 代理来源，按日期归档，最新日期在前。

[打开日期文件夹](https://github.com/JasperYubo/Fanqiang-Guide/tree/main/free-proxies)

## 继续阅读

- [全部资料](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/CATALOG.md)
- [软件动态](https://github.com/JasperYubo/Fanqiang-Guide/blob/main/UPDATES.md)
- [AI 资料入口](https://fanqiang.guide/ai/)
- [GitHub 知识库](https://github.com/JasperYubo/Fanqiang-Guide)

目录快照：2026-09-12。完整条目与来源见 GitHub 知识库。
