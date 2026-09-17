# 分类与关联设计 v0.1 · 2026-09-11

本库的目标是支持“找工具、理解关系、判断适配、追溯来源”。每个独立项目或概念使用稳定 ID，可同时关联多个平台和生态。名称、别名、分类、关系、来源、核验范围和变更记录由结构化数据维护；Markdown 是导入和阅读格式。

## 从设备到知识的层次

| 层次 | 回答的问题 | 典型实体 |
|---|---|---|
| 设备/系统 | 我在什么环境使用？ | Windows、Android、iOS、macOS、Linux、HarmonyOS、OpenWrt、华硕机型 |
| 产品/客户端 | 用户直接操作什么？ | Clash Verge Rev、v2rayNG、Shadowrocket |
| 内核 | 谁实际处理流量？ | Mihomo、sing-box、Xray-core |
| 协议/传输 | 两端如何配合？ | Shadowsocks、VLESS、Hysteria 2、REALITY、XHTTP |
| 固件/扩展环境 | 路由器能运行什么？ | ASUSWRT、Asuswrt-Merlin、GNUton、OpenWrt、Entware、软件中心 |
| 插件/管理工具 | 如何配置和管理？ | fancyss、MerlinClash、OpenClash、PassWall、面板与部署工具 |
| 配套能力 | DNS、分流和诊断由什么提供？ | SmartDNS、mosdns、规则集、订阅转换、NextTrace |
| 知识来源 | 结论依据是什么？ | 官方文档、README、发布说明、项目清单 |

分类可交叉。一个项目可以同时提供核心和客户端，但不能由“同名”推断所有平台实现一致。roles 保留合并时的多种角色；kind 是主分类。独立协议实体不计作可安装工具。

## 数据关系

- uses_core：客户端或插件使用某个内核。
- uses_protocol：项目使用某协议，避免把 Shadowsocks、WireGuard 协议误写成某个特定核心实现。
- uses_library：项目依赖开发库，例如 Ceno 与 Ouinet。
- plugin_for：扩展属于某固件/平台。
- fork_of：有明确依据的派生关系。
- implements / documented_implementation：项目实现某协议，或实现文档记录该协议/机制。
- related_to：明确标注为一般关联，不冒充继承或直接维护关系。

每条边有 evidence_url、verification_status；target_id 只在能定位到唯一实体时生成，否则保留 unresolved。关系的核验状态与实体核验状态独立。

## 核验粒度

primary_reviewed 表示已实际阅读该条目的第一方资料。它不等于全部字段已验证，更不等于安装成功、线路可用或软件安全。reviewed_fields 与 notes 表达核验边界。

reference_only 表示已收录发现线索，适合继续研究；historic 状态用于历史资料。来源声称的版本、价格、架构、源码状态保存在 source_claims，不能在合并时变成第一方验证事实。

缺失信息用 null/unknown 表达。不开出无来源的支持型号、效果评分或推荐排名。下载页面可达、仓库有星标、近期有提交均不能替代测试。

## 已知易混对象

- PassWall 和 PassWall2 是两个独立项目，不能把后者作为前者别名。
- sing-box 的核心、官方图形客户端和第三方使用该核心的客户端要区分。
- 原版 Merlin、GNUton 分支、梅林改版、华硕官改、软件中心和代理插件分别记录。
- 协议规范仓库与参考实现、生产客户端分别记录，例如 TUIC 与 AnyTLS 需要阅读仓库自身的范围说明。

## 后续扩展字段

正式产品阶段按需求追加有来源的 claims 表：entity_id、字段名、字段值、source_id、证据位置、适用版本、获取时间、审校时间、状态、替代旧声明。设备兼容使用独立矩阵：品牌、精确型号、硬件修订、CPU/ABI、固件分支与版本、插件版本、实测条件。人物与历史事件作为后续独立实体接入，避免仅为数量导入未经核验的小传。
