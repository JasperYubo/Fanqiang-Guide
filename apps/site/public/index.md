# 翻墙与科学上网工具指南

翻墙与科学上网工具指南：分清梯子、VPN 与代理，按设备查找客户端，理解机场、节点和订阅，并选择 OpenWrt、华硕梅林等路由器方案。

## 按设备选择

- Windows：v2rayN · Clash Verge Rev。[阅读指南](https://fanqiang.guide/guides/client-downloads.html)
- Android：v2rayNG · Hiddify。[阅读指南](https://fanqiang.guide/guides/client-downloads.html)
- iPhone / iPad：Shadowrocket · Hiddify。[阅读指南](https://fanqiang.guide/guides/shadowrocket-platforms.html)
- macOS：桌面客户端与版本。[阅读指南](https://fanqiang.guide/guides/client-downloads.html)
- Linux：客户端与核心。[阅读指南](https://fanqiang.guide/guides/proxy-cores.html)
- 华硕梅林：完整型号与固件分支。[阅读指南](https://fanqiang.guide/guides/asus-merlin.html)
- OpenWrt：OpenClash · PassWall。[阅读指南](https://fanqiang.guide/guides/openwrt-tools.html)

## 工具与问题

### [客户端下载：v2rayN、Clash、Hiddify](https://fanqiang.guide/guides/client-downloads.html)

按 Windows、Android、iPhone、macOS 与 Linux 选择 v2rayN、v2rayNG、Clash Verge Rev、Hiddify 或小火箭，从官方入口核对安装包和系统架构。

### [梯子、VPN 与代理的区别](https://fanqiang.guide/guides/ladder-vpn-proxy.html)

“梯子”是口语泛称，不是协议或软件；VPN、代理、客户端、节点和订阅属于不同层次。先确认设备、需要覆盖的流量范围及持有的配置类型，再选择相应工具。

### [机场、订阅与节点的区别](https://fanqiang.guide/guides/airport-subscription-nodes.html)

“机场”是网络社区对一类配置或节点服务的口语称呼；节点是一份服务器连接参数，订阅是客户端读取一组节点或完整配置的地址或文件。导入成功不等于节点当前可用。

### [免费节点：Clash 与 V2Ray 订阅来源](https://fanqiang.guide/guides/free-nodes.html)

每日资料通过固定文件夹进入，再选择日期文件。先辨认节点、订阅和 HTTP/SOCKS 代理的格式；资料收录与解析结果不等于连接可用性。

### [订阅转换：Sub-Store、subconverter](https://fanqiang.guide/guides/subscription-conversion.html)

订阅转换处理格式与字段。Sub-Store 偏向订阅管理，subconverter 提供格式转换，sub-web 提供前端界面；输出仍需与目标客户端逐项核对。

### [Shadowrocket 小火箭：下载与平台](https://fanqiang.guide/guides/shadowrocket-platforms.html)

Shadowrocket 的开发者商店页面列出 Apple 平台。搜索“安卓版”或“Windows 版”时，先确认项目身份，再按设备选择其他客户端。

### [小火箭节点二维码与订阅](https://fanqiang.guide/guides/shadowrocket-qr.html)

二维码承载文本，可能是单节点 URI、订阅地址、规则配置链接或普通网页。扫码识别、配置导入和实际连接是三个不同结果。

### [路由器翻墙与科学上网指南](https://fanqiang.guide/guides/router-guide.html)

路由器方案适合统一管理多台设备，但安装插件不会自动让所有流量按预期处理。先分清硬件、固件、插件、代理内核和配置，再选择 OpenWrt 或华硕梅林路线。

### [OpenWrt 路由器翻墙：OpenClash 与 PassWall2](https://fanqiang.guide/guides/openwrt-tools.html)

OpenWrt 是路由器系统，OpenClash 和 PassWall2 是其应用层项目。选择工具前，要核对设备、固件版本、内存、存储、包格式及内核依赖。

### [华硕梅林路由器翻墙：固件与插件](https://fanqiang.guide/guides/asus-merlin.html)

先确认完整型号与硬件修订，再区分原版 Merlin、GNUton 构建和带软件中心的改版环境。固件支持与 fancyss、MerlinClash 插件适配是两次不同的核对。

### [v2rayN 使用指南与工程书](https://fanqiang.guide/guides/v2rayn-guide.html)

从官方发布文件开始，先匹配系统与架构，再分清内核、单节点分享链接和订阅。配置导入、内核运行与实际连接应分别判断。

### [sing-box、Mihomo 与 Xray 内核](https://fanqiang.guide/guides/proxy-cores.html)

客户端提供管理界面，内核解释配置并处理流量。协议、规则、DNS 与 TUN 是不同层面的能力，选择时要核对对应项目及版本。

### [Clash Verge Rev 与相关项目](https://fanqiang.guide/guides/clash-projects.html)

Clash 相关名称覆盖桌面客户端、路由器插件和内核。先确认维护者、项目状态与设备平台，再选择下载入口；相似名称不能代替来源核对。

## Xray 与 sing-box 官方教程和配置文档

- [Xray 官方中文文档](https://xtls.github.io/)：快速入门、配置指南、入门与进阶技巧，以及 VLESS、REALITY 等技术资料。
- [sing-box 官方文档](https://sing-box.sagernet.org/)：客户端、服务端、DNS、路由和配置迁移说明，适合查配置与排错；站内可切换简体中文。

资料核对：2026-09-13。配置字段与版本变化以对应官方文档为准。

## 翻墙与科学上网常见问题

### 梯子就是 VPN 吗？

不是。“梯子”是口语泛称，可能指商业 VPN、代理客户端、节点服务或路由器方案；VPN 是其中一种技术或产品形态，两者不能直接画等号。

来源：[MDN Proxy server 术语说明](https://developer.mozilla.org/en-US/docs/Glossary/Proxy_server)；[NIST VPN 术语定义](https://csrc.nist.gov/glossary/term/virtual_private_network)；[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)

[查看完整答案与资料](https://fanqiang.guide/guides/ladder-vpn-proxy.html#question-1)

### 机场是一个客户端吗？

不是。“机场”通常指提供节点或订阅的一类服务，具体含义没有统一标准。v2rayN、Clash Verge Rev、Shadowrocket 等才是客户端或客户端项目。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)

[查看完整答案与资料](https://fanqiang.guide/guides/airport-subscription-nodes.html#question-1)

### OpenWrt 和 OpenClash 是同一个东西吗？

不是。OpenWrt 是路由器操作系统或固件环境，OpenClash 是运行在 OpenWrt LuCI 环境中的客户端项目；OpenClash 还会调用 Mihomo 等组件处理配置和流量。

来源：[OpenWrt 用户文档](https://openwrt.org/docs/guide-user/start)；[OpenClash 项目说明](https://github.com/vernesong/OpenClash)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

[查看完整答案与资料](https://fanqiang.guide/guides/router-guide.html#question-1)

### Windows、Mac 和安卓分别用哪个客户端？

v2rayN 和 Clash Verge Rev 面向 Windows、macOS 与 Linux，v2rayNG 面向 Android。Hiddify 的官方项目覆盖 Android、iOS、Windows、macOS 与 Linux。先按系统缩小选择，再对照对应发布页的处理器架构与系统要求。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[v2rayNG Android 项目](https://github.com/2dust/v2rayNG)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[Hiddify 官方项目与平台列表](https://github.com/hiddify/hiddify-app)

[查看完整答案与资料](https://fanqiang.guide/guides/client-downloads.html#question-1)

### 小火箭有安卓或 Windows 版吗？

Shadowrocket 的开发者 App Store 页面列出 Apple 平台，没有列出 Android 或 Windows 下载。安卓可查看 v2rayNG，Windows 可查看 v2rayN 或 Clash Verge Rev；这些是独立客户端，不是小火箭的同名版本。

来源：[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)；[v2rayNG Android 项目](https://github.com/2dust/v2rayNG)；[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)

[查看完整答案与资料](https://fanqiang.guide/guides/shadowrocket-platforms.html#question-1)

### Clash 和 V2Ray 免费节点在哪里按日期找？

Fanqiang Guide 的 free-proxies 文件夹按日期提供免费代理与节点来源记录。选择日期文件，可以查看当日收录的来源项目、资料格式和检查记录，再按客户端需要辨认节点列表、Clash YAML 或其他配置。

来源：[按日期查看免费代理与节点资料](https://github.com/JasperYubo/Fanqiang-Guide/tree/main/free-proxies)

[查看完整答案与资料](https://fanqiang.guide/guides/free-nodes.html#question-1)

### v2rayN 订阅导入了，为什么还不能连接？

v2rayN 接收订阅和内核完成连接是两个阶段。排查资料应包括当前 Xray、sing-box 等内核及版本、配置输入类型和完整错误现象，再区分程序启动、配置解析、路由或 DNS 问题；导入成功本身不能证明服务器可达。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Xray-core 项目](https://github.com/XTLS/Xray-core)；[sing-box TUN 配置文档](https://sing-box.sagernet.org/configuration/inbound/tun/)

[查看完整答案与资料](https://fanqiang.guide/guides/v2rayn-guide.html#question-3)

### 小火箭节点二维码和订阅地址有什么区别？

小火箭节点二维码可以承载一个服务器的分享 URI，订阅地址则用于取得一组配置；二维码也可以承载订阅地址。区分两者要看二维码里的文本及链接实际提供的内容，而不是图片外观。

来源：[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

[查看完整答案与资料](https://fanqiang.guide/guides/shadowrocket-qr.html#question-1)

## 免费节点与代理来源归档

[按日期查看公开来源](https://github.com/JasperYubo/Fanqiang-Guide/tree/main/free-proxies)

需要继续处理设备问题，可以把对应专题的 I-Lang 工程书交给自己的 AI。


## 资料查询

- [代理工具与开源项目资料库（310条）](https://fanqiang.guide/guides/library.html)
- [58条梅林型号支持记录](https://fanqiang.guide/guides/merlin-models.html)
- [资料收录与核对方法](https://fanqiang.guide/guides/about.html)
