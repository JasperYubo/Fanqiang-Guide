# 订阅转换怎么选：Sub-Store、subconverter 与 sub-web 的区别

订阅转换处理格式与字段。Sub-Store 偏向订阅管理，subconverter 提供格式转换，sub-web 提供前端界面；输出仍需与目标客户端逐项核对。

整理日期：2026-09-13。具体版本、平台与型号以所引来源为准。

原文：https://fanqiang.guide/guides/subscription-conversion.html

## 三个项目各自做什么

Sub-Store 提供订阅管理能力；subconverter 负责在不同订阅格式间转换；sub-web 是订阅转换的 Web 前端。界面与实际执行转换的服务应分别辨认。

- 管理多份来源、组合输出：查看 Sub-Store 的当前功能。
- 需要指定来源与目标格式：查看 subconverter 的支持范围。
- 看到 sub-web 界面时，还要知道它使用哪个转换后端。

来源：[Sub-Store 项目](https://github.com/sub-store-org/Sub-Store)；[subconverter 项目](https://github.com/tindy2013/subconverter)；[sub-web 项目](https://github.com/CareyWang/sub-web)

## 先写清输入和目标

转换任务至少需要来源格式、目标客户端及版本。文件扩展名、订阅名称或“通用”标签都不足以表达全部兼容条件；协议、传输方式和规则能力也会影响结果。

- 输入：单节点分享 URI、通用节点列表，还是完整配置。
- 目标：客户端名称、内核、版本和接受的格式。
- 期望保留：节点名称、协议参数、分组、规则和 DNS 设置。

来源：[subconverter 项目](https://github.com/tindy2013/subconverter)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

## 转换成功以后看什么

输出能被解析，说明格式检查通过；它不证明所有语义都保留，也不证明服务器可达。节点字段与完整的路由、DNS 配置需要分别对照。

- 检查节点数量与被过滤项目，不把过滤当成新增节点。
- 对照目标格式无法表达的字段，列明差异。
- 订阅更新后仍应复核输出，不能用一次结果保证以后都相同。

来源：[subconverter 项目](https://github.com/tindy2013/subconverter)；[Sub-Store 项目](https://github.com/sub-store-org/Sub-Store)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

## 常见问题

### Clash 订阅转换可以用什么工具？

subconverter 提供订阅格式转换，Sub-Store 提供订阅管理，sub-web 提供转换的网页界面。选择项目时应明确原始输入、目标客户端与内核版本；网页前端的名称还不能说明实际由哪个后端处理转换。

来源：[subconverter 项目](https://github.com/tindy2013/subconverter)；[Sub-Store 项目](https://github.com/sub-store-org/Sub-Store)；[sub-web 项目](https://github.com/CareyWang/sub-web)

### 把订阅交给自己的 AI 转换，需要提供哪些信息？

订阅转换需要原始输入的类型、目标客户端及版本，以及要保留的节点、分组、规则和 DNS 设置。单节点 URI、节点列表与完整配置是不同输入；这些信息能让自己的 AI 对照转换器和目标内核文档判断可保留的内容。

来源：[subconverter 项目](https://github.com/tindy2013/subconverter)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

### 订阅文件改成 YAML 后，为什么还是导不进 Clash？

Mihomo 读取的是符合配置文档的结构与字段，修改文件后缀不会转换内容。原始节点列表或其他客户端配置需要按目标格式处理，再核对协议参数、分组、规则与 DNS 字段；YAML 后缀本身不说明配置是否合格。

来源：[Mihomo 配置文档](https://wiki.metacubex.one/config/)；[subconverter 项目](https://github.com/tindy2013/subconverter)

### 订阅转换成功后，原来的规则和 DNS 会都保留吗？

订阅转换的输出能被解析，只能说明它通过了相应格式检查。节点字段、分组、路由和 DNS 的表达方式可能不同，需要分别对照目标内核；转换结果应列出保留、改变和无法表达的内容，而不是只给一个“成功”。

来源：[subconverter 项目](https://github.com/tindy2013/subconverter)；[Sub-Store 项目](https://github.com/sub-store-org/Sub-Store)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

## 交给自己的 AI 继续处理

工程书包含资料、待确认设备信息、检查项和交付要求。

[I-Lang 工程书](https://fanqiang.guide/guides/subscription-conversion.ilang)

[返回指南目录](https://fanqiang.guide/guides/index.html)
