# 机场、订阅和节点是什么？Clash 与 V2Ray 新手说明

“机场”是网络社区对一类配置或节点服务的口语称呼；节点是一份服务器连接参数，订阅是客户端读取一组节点或完整配置的地址或文件。导入成功不等于节点当前可用。

整理日期：2026-09-19。具体版本、平台与型号以所引来源为准。

原文：https://fanqiang.guide/guides/airport-subscription-nodes.html

## 机场、订阅、节点和客户端的关系

“机场”是网络社区对一类配置或节点服务的口语称呼，不是标准技术名称。节点是一份服务器连接参数；订阅是客户端用来取得一组节点或完整配置的地址或文件；客户端负责读取配置并调用内核建立连接。

常见链路可以理解为“配置来源或服务—订阅—客户端—节点—远端连接”。其中每一层都可以独立变化：一个订阅可能包含多个节点，一个节点也可以通过单独的分享链接导入，同一订阅则不一定适合所有客户端。

- 订阅不是代理协议，协议和参数位于订阅返回的具体内容中。
- 客户端解析成功不等于远端服务器当前可达。
- 订阅地址如果包含账户令牌或访问凭据，应像密码一样保管。

来源：[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

## 怎样识别单节点、订阅、配置文件和二维码

ss、vmess、vless、trojan 等 URI 通常表达单节点参数；HTTPS 地址可能是订阅接口、配置文件或普通网页；YAML 和 JSON 可能保存节点列表或完整配置；IP、端口列表则可能属于 HTTP/SOCKS 代理资料。

二维码只承载文本，里面可以是单节点 URI、订阅地址、配置链接或普通网页。应先识别解码后的内容，再判断目标客户端是否支持，而不是根据二维码图片或文件后缀猜测用途。

- 修改文件后缀不会把一种配置转换成另一种格式。
- Base64 只是一种编码外观，仍需查看解码后的实际内容。
- HTTP/SOCKS 地址列表不能仅凭“免费代理”四个字当成 Clash 或 V2Ray 订阅。

来源：[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

## 导入、连接与订阅转换要分别判断

订阅无法使用时，依次检查地址是否能读取、返回内容是否符合预期、客户端能否解析、内核是否支持协议字段、节点是否可达，以及路由和 DNS 是否命中。把这些阶段合并成“订阅不能用”，会丢失定位所需的信息。

输入与目标客户端格式不一致时可以评估 Sub-Store、subconverter 或 sub-web 等项目。转换结果能被解析，只说明格式检查通过；节点、分组、规则和 DNS 语义是否保留，仍需逐项对照。

- 免费或付费只描述获取方式，不能直接证明速度、安全性或持续时间。
- 来源访问、格式解析和用户设备连接测试应分别记录。
- 历史日期页引用的上游链接可能继续变化，不能自动视为全部原始节点的不可变备份。

来源：[Sub-Store 项目](https://github.com/sub-store-org/Sub-Store)；[subconverter 项目](https://github.com/tindy2013/subconverter)；[sub-web 项目](https://github.com/CareyWang/sub-web)；[按日期查看免费代理与节点资料](https://github.com/JasperYubo/Fanqiang-Guide/tree/main/free-proxies)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

## 常见问题

### 机场是一个客户端吗？

不是。“机场”通常指提供节点或订阅的一类服务，具体含义没有统一标准。v2rayN、Clash Verge Rev、Shadowrocket 等才是客户端或客户端项目。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)

### 一个订阅就是一个节点吗？

不是。订阅通常返回一组节点或一份完整配置，节点则是一份具体连接参数。订阅也可能只返回少量内容，因此应查看实际响应而不是按名称推断。

来源：[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)

### Clash 订阅可以直接导入 v2rayN 吗？

不能只看订阅名称判断。需要检查实际返回格式、其中的协议，以及目标客户端和内核版本。格式不匹配时可能需要转换，但转换后仍要核对丢失或改变的字段。

来源：[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[subconverter 项目](https://github.com/tindy2013/subconverter)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

### 二维码一定是小火箭节点吗？

不是。二维码可以承载单节点链接、订阅地址、配置链接或普通网页。应先识别其中的文本和响应内容，再决定使用哪个客户端处理。

来源：[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

### 为什么订阅导入成功后仍然不能连接？

导入成功只说明客户端读取并解析了某种内容。还需检查内核对协议字段的支持、节点当前可达性、路由、DNS 和系统权限，不能把解析结果当作连接证据。

来源：[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)；[sing-box 官方文档](https://sing-box.sagernet.org/)；[Xray 官方中文文档](https://xtls.github.io/)

### 订阅链接可以公开发给别人帮忙看吗？

不建议公开发送。订阅地址可能包含账户令牌或访问凭据。排错时应隐藏敏感参数，只提供返回格式、客户端、版本和具体错误阶段。

来源：[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Sub-Store 项目](https://github.com/sub-store-org/Sub-Store)

## 交给自己的 AI 继续处理

工程书包含资料、待确认设备信息、检查项和交付要求。

[I-Lang 工程书](https://fanqiang.guide/guides/airport-subscription-nodes.ilang)

[返回指南目录](https://fanqiang.guide/guides/index.html)
