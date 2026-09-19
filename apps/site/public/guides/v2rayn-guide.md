# v2rayN 使用指南与工程书：版本、内核、订阅和配置

从官方发布文件开始，先匹配系统与架构，再分清内核、单节点分享链接和订阅。配置导入、内核运行与实际连接应分别判断。

整理日期：2026-09-13。具体版本、平台与型号以所引来源为准。

原文：https://fanqiang.guide/guides/v2rayn-guide.html

## 项目与发布文件怎样对应

当前 v2rayN 面向 Windows、Linux、macOS。官方发布文件说明区分系统、架构和包内组件；同一版本出现多个附件，是因为它们用途不同。

- 版本号相同，x64 与 ARM64 仍不能混为一谈。
- 先核对发布文件说明，再区分便携包、安装包与运行环境。
- Android 对应的是另一个项目 v2rayNG。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[v2rayN 发布文件说明](https://github.com/2dust/v2rayN/wiki/Release-files-introduction)；[v2rayNG Android 项目](https://github.com/2dust/v2rayNG)

## 内核和界面各自负责什么

v2rayN 作为图形客户端管理配置，并支持调用 Xray、sing-box 等内核。界面版本与内核版本不是一个编号；某功能是否存在，要同时看所选内核及其配置。

- 记录客户端版本、当前内核与内核版本。
- 导入成功只表示客户端接收了资料，后续还要判断内核运行状态。
- 不要从界面显示的节点名称推断协议参数已经完整。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Xray-core 项目](https://github.com/XTLS/Xray-core)

## 单节点分享与订阅更新

官方文档区分协议标准分享格式与 v2rayN 内部格式。内部格式可以携带标准分享方案之外的字段，但不能据此保证其他客户端也能识别。

- 单节点分享资料用于描述一个配置；订阅地址用于取得一组配置。
- 迁移给其他客户端前，标明原始格式与必须保留的字段。
- 更新订阅改变的是取回的配置，规则与本地设置是否变化需要另外核对。

来源：[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

## 排查时把现象分开

“不能用”可能指打不开程序、无法导入、内核未运行，或者已有连接请求但没有得到预期结果。这些现象需要不同证据。

- 程序问题：系统、架构、版本与启动错误。
- 配置问题：输入格式及脱敏后的解析错误。
- 网络行为问题：内核、路由、DNS 与具体目标的现象。

来源：[v2rayN 发布文件说明](https://github.com/2dust/v2rayN/wiki/Release-files-introduction)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[sing-box TUN 配置文档](https://sing-box.sagernet.org/configuration/inbound/tun/)

## 常见问题

### v2rayN 配置前要准备哪些资料？

v2rayN 配置需要操作系统与架构、客户端版本、所用内核，以及已有的节点分享链接、订阅地址或配置文件。官方发布说明用于核对程序包，订阅说明用于辨认输入；把这些资料交给自己的 AI，比只说“v2rayN 不能用”更容易定位下一步。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[v2rayN 发布文件说明](https://github.com/2dust/v2rayN/wiki/Release-files-introduction)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

### v2rayN 分享的链接为什么在其他客户端导不进去？

v2rayN 同时有协议标准分享格式和内部分享格式，内部格式可以携带标准提案以外的字段。其他客户端是否能导入，取决于它接受的格式与字段；跨客户端迁移时需要辨认原始格式，而不只是复制同一段链接。

来源：[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)

### v2rayN 订阅导入了，为什么还不能连接？

v2rayN 接收订阅和内核完成连接是两个阶段。排查资料应包括当前 Xray、sing-box 等内核及版本、配置输入类型和完整错误现象，再区分程序启动、配置解析、路由或 DNS 问题；导入成功本身不能证明服务器可达。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[Xray-core 项目](https://github.com/XTLS/Xray-core)；[sing-box TUN 配置文档](https://sing-box.sagernet.org/configuration/inbound/tun/)

## 交给自己的 AI 继续处理

工程书包含资料、待确认设备信息、检查项和交付要求。

[I-Lang 工程书](https://fanqiang.guide/guides/v2rayn-guide.ilang)

[返回指南目录](https://fanqiang.guide/guides/index.html)
