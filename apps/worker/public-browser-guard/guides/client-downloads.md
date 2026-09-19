# 客户端下载与系统选择：v2rayN、v2rayNG、Clash Verge Rev、Hiddify

按 Windows、Android、iPhone、macOS 与 Linux 选择 v2rayN、v2rayNG、Clash Verge Rev、Hiddify 或小火箭，从官方入口核对安装包和系统架构。

整理日期：2026-09-13。具体版本、平台与型号以所引来源为准。

原文：https://fanqiang.guide/guides/client-downloads.html


## 按系统与架构找官方发布入口

先找到系统与处理器架构，再核对官方发布页中的对应附件。

| 系统与架构 | 客户端 | 发布入口 | 附件核对 |
| --- | --- | --- | --- |
| Windows / x64、ARM64 | v2rayN | [官方发布入口](https://github.com/2dust/v2rayN/releases/latest) | 在附件中按 windows-64 或 windows-arm64 区分；ZIP 为便携包，带 desktop 的附件使用另一套桌面界面。（核对：2026-09-12） [依据 1](https://github.com/2dust/v2rayN/releases/tag/7.24.9) · [依据 2](https://github.com/2dust/v2rayN/wiki/Release-files-introduction) |
| macOS / Intel x64、Apple Silicon ARM64 | v2rayN | [官方发布入口](https://github.com/2dust/v2rayN/releases/latest) | 按 macos-64 或 macos-arm64 选择；发布附件提供 DMG 与 ZIP，下载前同时核对系统版本要求。（核对：2026-09-12） [依据 1](https://github.com/2dust/v2rayN/releases/tag/7.24.9) · [依据 2](https://github.com/2dust/v2rayN/wiki/Release-files-introduction) |
| Linux / 常见组合：x64、ARM64 | v2rayN | [官方发布入口](https://github.com/2dust/v2rayN/releases/latest) | 按 linux-64 或 linux-arm64 匹配架构；Debian/Ubuntu 查看 DEB，Fedora/Red Hat 查看 RPM，也有 ZIP。其他架构以正式附件为准。（核对：2026-09-12） [依据 1](https://github.com/2dust/v2rayN/releases/tag/7.24.9) · [依据 2](https://github.com/2dust/v2rayN/wiki/Release-files-introduction) |
| Windows / x64、ARM64 | Clash Verge Rev | [官方发布入口](https://github.com/clash-verge-rev/clash-verge-rev/releases/latest) | 已核对正式附件中的 x64-setup.exe 与 arm64-setup.exe；同时提供 fixed_webview2 包型，按发布说明选择。（核对：2026-09-12） [依据 1](https://github.com/clash-verge-rev/clash-verge-rev/releases/tag/v2.5.2) · [依据 2](https://github.com/clash-verge-rev/clash-verge-rev) |
| macOS / Intel x64、Apple Silicon ARM64 | Clash Verge Rev | [官方发布入口](https://github.com/clash-verge-rev/clash-verge-rev/releases/latest) | DMG 附件用 x64 区分 Intel，aarch64 区分 Apple Silicon；同时核对该版本的 macOS 要求。（核对：2026-09-12） [依据 1](https://github.com/clash-verge-rev/clash-verge-rev/releases/tag/v2.5.2) · [依据 2](https://github.com/clash-verge-rev/clash-verge-rev) |
| Linux / x64、ARM64、ARMHF | Clash Verge Rev | [官方发布入口](https://github.com/clash-verge-rev/clash-verge-rev/releases/latest) | DEB 用 amd64、arm64、armhf 标记，RPM 用 x86_64、aarch64、armhfp 标记；包格式和架构都要匹配发行版。（核对：2026-09-12） [依据 1](https://github.com/clash-verge-rev/clash-verge-rev/releases/tag/v2.5.2) |
| Android / arm64-v8a、armeabi-v7a、x86、x86_64 | v2rayNG | [官方发布入口](https://github.com/2dust/v2rayNG/releases/latest) | APK 文件名标明设备 ABI；按系统支持的 ABI 选择。发布页中的 .sig 是签名附件，应用安装包后缀为 .apk。（核对：2026-09-12） [依据 1](https://github.com/2dust/v2rayNG/releases/tag/2.2.6) · [依据 2](https://github.com/2dust/v2rayNG) |
| Android / ARM64、ARMv7、x86_64；另有 universal 包 | Hiddify | [官方发布入口](https://github.com/hiddify/hiddify-app/releases/latest) | 正式发布列出 Android-arm64、Android-arm7、Android-x86_64 与 Android-universal APK；按设备及发布说明选择。（核对：2026-09-12） [依据 1](https://github.com/hiddify/hiddify-app/releases/tag/v4.1.1) · [依据 2](https://github.com/hiddify/hiddify-app) |
| iPhone / iPad / 按 App Store 设备兼容性选择 | Hiddify | [官方发布入口](https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532) | 官方项目 README 指向此 App Store 应用；核对商店的设备、系统及地区条件。（核对：2026-09-12） [依据 1](https://github.com/hiddify/hiddify-app) · [依据 2](https://raw.githubusercontent.com/hiddify/hiddify-app/main/README.md) · [依据 3](https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532) |
| iPhone / iPad / 按 App Store 设备兼容性选择 | Shadowrocket | [官方发布入口](https://apps.apple.com/us/app/shadowrocket/id932747118) | 开发者的 Apple 商店应用，应用 ID 为 932747118；查看商店兼容性列表确认设备系统要求。（核对：2026-09-12） [依据 1](https://apps.apple.com/us/app/shadowrocket/id932747118) |

[全部工具目录](https://fanqiang.guide/guides/library.html)

## 按操作系统缩小选择

v2rayN 的当前项目面向 Windows、Linux 和 macOS；v2rayNG 面向 Android。Clash Verge Rev 也是桌面客户端，项目说明列出 Windows、macOS 与 Linux。

Hiddify 的官方项目列出 Android、iOS、Windows、macOS 和 Linux，并提供各平台下载入口。它基于 sing-box，支持订阅链接及多种配置格式；仍需按当前版本核对具体字段和系统要求。

- 桌面设备：从 v2rayN 或 Clash Verge Rev 的项目页进入 Releases。
- 安卓设备：v2rayNG 的 APK 来自它自己的发布页。
- Apple 设备：Shadowrocket 的开发者入口是 App Store，按商店兼容性列表核对设备。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[v2rayNG Android 项目](https://github.com/2dust/v2rayNG)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)；[Hiddify 官方项目与平台列表](https://github.com/hiddify/hiddify-app)

## 安装包要同时匹配系统和架构

同一个发布页可能同时提供 x64、ARM64、安装包、便携包和源代码压缩包。文件名里的系统与架构决定用途；Source code 压缩包供构建使用，不能等同于已经打包的客户端。

- 先确认操作系统版本和处理器架构，再对照该版本的发布说明。
- v2rayN 的发布文件说明还区分内核与运行环境是否随包提供。
- 页面名称相似不等于维护者相同，下载前对照仓库所有者和正式发布入口。

来源：[v2rayN 发布文件说明](https://github.com/2dust/v2rayN/wiki/Release-files-introduction)；[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)

## 下载完成后还缺哪些资料

客户端负责管理配置并调用内核；配置则描述使用哪个服务器、什么协议以及怎样分流。只拿到客户端安装包，还不足以判断能否完成连接。

- 准备客户端与内核的准确版本。
- 确认手里是单节点分享链接、订阅地址，还是完整配置文件。
- 把缺失的参数列出来，交给自己的 AI 根据对应官方文档继续核对。

来源：[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)

## 常见问题

### Windows、Mac 和安卓分别用哪个客户端？

v2rayN 和 Clash Verge Rev 面向 Windows、macOS 与 Linux，v2rayNG 面向 Android。Hiddify 的官方项目覆盖 Android、iOS、Windows、macOS 与 Linux。先按系统缩小选择，再对照对应发布页的处理器架构与系统要求。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[v2rayNG Android 项目](https://github.com/2dust/v2rayNG)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[Hiddify 官方项目与平台列表](https://github.com/hiddify/hiddify-app)

### v2rayN、v2rayNG 和 Clash 的官方下载在哪里？

v2rayN 与 v2rayNG 分别从 2dust 名下的同名 GitHub 仓库进入 Releases；Clash Verge Rev 从 clash-verge-rev/clash-verge-rev 项目进入发布页。“Clash”还用于其他项目名称，下载前应确认具体客户端和维护者。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[v2rayNG Android 项目](https://github.com/2dust/v2rayNG)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)

### 下载页里的 x64、ARM64 和 Source code 应该怎么区分？

客户端的 x64、ARM64 标记用于区分处理器架构，Windows、macOS、Linux 标记用于区分系统。Source code 是源码压缩包，和可运行的客户端发布包用途不同；v2rayN 的发布文件说明还区分便携包、安装包与随包提供的内核。

来源：[v2rayN 发布文件说明](https://github.com/2dust/v2rayN/wiki/Release-files-introduction)；[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)

### 客户端装好了，是不是就已经有节点了？

客户端安装包提供软件，节点参数和订阅地址提供连接配置。v2rayN 将订阅地址、协议分享格式和内部格式单独说明；下载软件以后，还需要与你所用客户端相符的配置资料。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

## 交给自己的 AI 继续处理

工程书包含资料、待确认设备信息、检查项和交付要求。

[I-Lang 工程书](https://fanqiang.guide/guides/client-downloads.ilang)

[返回指南目录](https://fanqiang.guide/guides/index.html)
