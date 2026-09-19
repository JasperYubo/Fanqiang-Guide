# 小火箭节点二维码与订阅二维码：先分清里面装的是什么

二维码承载文本，可能是单节点 URI、订阅地址、规则配置链接或普通网页。扫码识别、配置导入和实际连接是三个不同结果。

整理日期：2026-09-19。具体版本、平台与型号以所引来源为准。

原文：https://fanqiang.guide/guides/shadowrocket-qr.html

## 二维码不是一种代理协议

先辨认二维码解码后的内容，再讨论如何交给客户端。图片外观不能证明里面是节点还是订阅；即使以 HTTPS 开头，也要确认它指向配置集合、规则文件还是网页。

- 单节点 URI：例如 Shadowsocks SIP002 定义的 ss 协议分享格式。
- 在线配置：例如 SIP008 定义由 HTTPS 取得的 JSON 服务器数组。
- 以上是两种规范的区别，不代表 Shadowrocket 自动支持每一种规范或变体。

来源：[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)

## 单个节点与订阅为什么不同

一个单节点分享 URI 描述的是一份服务器参数；订阅则需要客户端按地址读取内容。把单个 URI 做成二维码，不会因此产生可自动更新的订阅来源。

- 判断更新能力，要看客户端是否保存了订阅来源及其当前返回内容。
- 协议字段、插件参数或客户端专有字段，可能影响跨客户端识别。
- Base64 是编码方式，本身不构成加密或兼容性保证。

来源：[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

## 扫码后应该分三层看结果

二维码被识别，只说明文本被读出。配置被导入，还要看字段是否被目标版本接受。最终是否连接成功，需要用户设备与网络的实际结果。

- 识别层：解码内容属于哪一种资料。
- 配置层：目标客户端是否接受这种格式与字段。
- 连接层：由用户自己的 AI 根据实际现象继续核对，不能从前两层代推。

来源：[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

## 常见问题

### 小火箭节点二维码和订阅地址有什么区别？

小火箭节点二维码可以承载一个服务器的分享 URI，订阅地址则用于取得一组配置；二维码也可以承载订阅地址。区分两者要看二维码里的文本及链接实际提供的内容，而不是图片外观。

来源：[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

### 小火箭能扫出二维码，为什么还是导入失败？

小火箭识别二维码只完成了文本读取，导入还需要内容符合客户端支持的格式与字段。单节点 URI、在线配置和普通网页链接用途不同；判断原因需要原始内容类型、客户端版本与导入错误，不能只看扫码是否成功。

来源：[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Shadowrocket 开发者 App Store 页面](https://apps.apple.com/us/app/shadowrocket/id932747118)

### 把一个节点做成二维码后，会自动更新吗？

单节点二维码仍然保存那份服务器分享信息，不会因为变成图片就成为订阅来源。订阅更新依赖客户端保存的来源地址及该地址返回的配置；判断能否更新，应先分清二维码装的是单节点 URI 还是在线配置入口。

来源：[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

### 二维码里是 HTTPS 链接，就一定是订阅吗？

HTTPS 链接说明访问方式，不能单独说明二维码内容是订阅。该地址可能返回服务器列表、规则文件或普通网页；例如 SIP008 对在线配置规定了 JSON 服务器数组，因此仍要对照响应内容与客户端接受的格式。

来源：[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

## 交给自己的 AI 继续处理

工程书包含资料、待确认设备信息、检查项和交付要求。

[I-Lang 工程书](https://fanqiang.guide/guides/shadowrocket-qr.ilang)

[返回指南目录](https://fanqiang.guide/guides/index.html)
