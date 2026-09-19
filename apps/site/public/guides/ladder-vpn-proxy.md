# 梯子、VPN 和代理有什么区别？科学上网新手选择指南

“梯子”是口语泛称，不是协议或软件；VPN、代理、客户端、节点和订阅属于不同层次。先确认设备、需要覆盖的流量范围及持有的配置类型，再选择相应工具。

整理日期：2026-09-19。具体版本、平台与型号以所引来源为准。

原文：https://fanqiang.guide/guides/ladder-vpn-proxy.html

## 梯子、VPN、代理、客户端和节点分别是什么

“梯子”是中文网络中的口语泛称，可能指 VPN 服务、代理客户端、节点服务或整套路由器方案，本身不是固定协议。VPN 通常在设备与远端网络之间建立虚拟网络通道；代理则按照应用、系统代理或路由规则转发被选中的连接。

v2rayN、Clash Verge Rev、Shadowrocket 等主要是客户端或客户端项目；客户端负责读取配置并调用内核，节点提供服务器连接参数，订阅则用于取得一组节点或完整配置。安装客户端不等于已经拥有节点。

- VPN、代理和“梯子”不是三个可以直接互换的产品名称。
- 系统显示 VPN 图标，不能单独证明底层使用的是哪种协议或配置方式。
- 客户端、代理内核、节点与订阅应分别记录，不能只用一个软件名称概括全部链路。

来源：[MDN Proxy server 术语说明](https://developer.mozilla.org/en-US/docs/Glossary/Proxy_server)；[NIST VPN 术语定义](https://csrc.nist.gov/glossary/term/virtual_private_network)；[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

## 新手按设备、覆盖范围和配置类型选择

先确认 Windows、macOS、Linux、Android、iPhone 还是路由器，再从对应项目或应用商店的正式入口选择客户端。随后确认只需处理单个应用、整台设备，还是希望多台家庭设备共用规则。

最后辨认手中的输入是单节点分享链接、订阅地址、完整 YAML 或 JSON 配置，还是 HTTP/SOCKS 地址列表。相同协议可能由不同客户端支持，但完整配置中的分组、规则和 DNS 字段未必通用。

- 单台电脑或手机通常先从设备客户端开始，安装和排错范围更小。
- 需要多台固定设备共用规则时，再评估路由器方案。
- 导入成功只说明客户端读到了内容，不代表服务器当前可达或全部流量已经按预期处理。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)

## 客户端、内核和实际流量要分层检查

客户端提供配置管理界面，Mihomo、Xray、sing-box 等内核负责解释配置并处理流量。排查时应同时记录客户端、内核、系统和输入类型，再区分失败发生在导入、内核启动、服务器连接、DNS 还是路由阶段。

TUN 或系统代理开关处于启用状态，不能单独证明每个应用的所有连接都经过代理；实际结果还受系统权限、路由、DNS、IPv4、IPv6 和应用行为影响。

- 下载软件时核对项目所有者、正式发布入口、系统和处理器架构。
- 未知代理可能接触连接元数据及未被端到端加密的内容，不能仅凭“免费”或“付费”判断可信度。
- 没有同一设备、网络与时间下的可复现实测，不按 VPN 或代理的名称给出速度排名。

来源：[Mihomo 配置文档](https://wiki.metacubex.one/config/)；[sing-box 官方文档](https://sing-box.sagernet.org/)；[Xray 官方中文文档](https://xtls.github.io/)；[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)

## 常见问题

### 梯子就是 VPN 吗？

不是。“梯子”是口语泛称，可能指商业 VPN、代理客户端、节点服务或路由器方案；VPN 是其中一种技术或产品形态，两者不能直接画等号。

来源：[MDN Proxy server 术语说明](https://developer.mozilla.org/en-US/docs/Glossary/Proxy_server)；[NIST VPN 术语定义](https://csrc.nist.gov/glossary/term/virtual_private_network)；[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)

### VPN 和代理哪个速度更快？

仅凭技术名称不能判断速度。服务器位置、网络路径、协议、拥塞、设备性能和规则都会影响结果；没有同一环境下的可复现实测，就不应给出固定速度排名。

来源：[Mihomo 配置文档](https://wiki.metacubex.one/config/)；[sing-box 官方文档](https://sing-box.sagernet.org/)；[Xray 官方中文文档](https://xtls.github.io/)

### Clash、v2rayN 和小火箭都是 VPN 吗？

这些名称通常指客户端或相关项目，它们读取配置并调用相应内核。平台可能借助系统 VPN 接口处理流量，但界面中的 VPN 标识不能代替对客户端、内核和协议的具体判断。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

### 客户端安装好以后还需要节点或订阅吗？

通常仍需要兼容的节点、订阅或完整配置。客户端是软件，节点和订阅提供连接参数；程序安装成功、配置导入成功和服务器连接成功是三项不同结果。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

### 一台电脑能用的配置，手机也能直接用吗？

不一定。需要同时核对手机客户端、配置格式、协议和版本。单个节点参数可能可以迁移，完整配置中的规则、DNS 和平台字段则未必通用。

来源：[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)；[sing-box 官方文档](https://sing-box.sagernet.org/)

## 交给自己的 AI 继续处理

工程书包含资料、待确认设备信息、检查项和交付要求。

[I-Lang 工程书](https://fanqiang.guide/guides/ladder-vpn-proxy.ilang)

[返回指南目录](https://fanqiang.guide/guides/index.html)
