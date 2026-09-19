# 华硕梅林路由器翻墙与科学上网：AX86U、AX58U 固件及插件

先确认完整型号与硬件修订，再区分原版 Merlin、GNUton 构建和带软件中心的改版环境。固件支持与 fancyss、MerlinClash 插件适配是两次不同的核对。

整理日期：2026-09-19。具体版本、平台与型号以所引来源为准。

原文：https://fanqiang.guide/guides/asus-merlin.html


## 梅林型号支持速查

来源列入支持不表示本站设备实测；插件环境单独核对。

| 完整型号 | 固件分支 | 来源状态 | 来源与日期 |
| --- | --- | --- | --- |
| RT-AX58U V1 | Asuswrt-Merlin 原版 | 来源列入支持 | [来源](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices) · 2026-09-11 |
| RT-AX86U | Asuswrt-Merlin 原版 | 来源列入支持 | [来源](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices) · 2026-09-11 |
| RT-AC68U | Asuswrt-Merlin 原版 | 来源明确不支持 | [来源](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices) · 2026-09-11 |
| RT-AX58U v2 | GNUton | 来源列入支持 | [来源](https://github.com/gnuton/asuswrt-merlin.ng) · 2026-09-11 |
| DSL-AC68U | GNUton | 来源列入支持 | [来源](https://github.com/gnuton/asuswrt-merlin.ng) · 2026-09-11 |

[查询全部58条型号记录](https://fanqiang.guide/guides/merlin-models.html)

## 梅林不是一个通用安装包

Asuswrt-Merlin 原版与 GNUton 构建各自列出设备支持范围。fancyss、MerlinClash 属于插件项目，不能用“固件能刷”代替“插件能装”的判断。

- 固件层：记录项目名称、版本和完整设备型号。
- 环境层：确认是否具备目标插件要求的软件中心等条件。
- 插件层：再核对平台包、依赖和当前发布说明。

来源：[Asuswrt-Merlin 官方支持设备表](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices)；[GNUton 构建与支持设备](https://github.com/gnuton/asuswrt-merlin.ng)；[fancyss 固件环境与平台包说明](https://github.com/hq450/fancyss)；[MerlinClash 项目说明](https://github.com/rts600/MerlinClash/blob/main/README.md)

## AX58U V1、V2 与 AC68U 的实际区别

原版 Merlin 的支持表明确列出 RT-AX58U V1／RT-AX3000 V1；GNUton 项目另列 RT-AX58U V2。因此省略 V1、V2 会把不同支持分支混在一起。

- 原版表将 RT-AC68U 的所有版本列入不再支持设备。
- GNUton 列有 DSL-AC68U，DSL 与 RT 前缀不能省略。
- RT-AX86U 与 RT-AX86U PRO 也应分别按完整名称核对。

来源：[Asuswrt-Merlin 官方支持设备表](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices)；[GNUton 构建与支持设备](https://github.com/gnuton/asuswrt-merlin.ng)

## fancyss 包型与固件支持分开看

fancyss 说明要求基于 Asuswrt／Merlin 且带软件中心的相应固件环境，并区分平台包与 full、lite 包型。某款设备在插件表出现，并不改变原版固件项目对它的维护状态。

- 平台包要对照设备平台与架构，不按名称相近选择。
- full、lite 的功能与空间需求不同，按项目当前说明核对。
- MerlinClash 使用自己的项目说明与包来源；不要把一个插件的支持表转用给另一个。

来源：[fancyss 固件环境与平台包说明](https://github.com/hq450/fancyss)；[MerlinClash 项目说明](https://github.com/rts600/MerlinClash/blob/main/README.md)；[Asuswrt-Merlin 官方支持设备表](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices)

## 常见问题

### 华硕梅林支持哪些型号，去哪里查？

Asuswrt-Merlin 原版的支持范围查官方 Supported Devices 表，GNUton 构建查 GNUton 自己的设备列表。型号要保留 RT/DSL 前缀及 V1、V2、PRO 等标记；固件支持和插件适配分别查各自项目，不能合并成一个通用支持结论。

来源：[Asuswrt-Merlin 官方支持设备表](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices)；[GNUton 构建与支持设备](https://github.com/gnuton/asuswrt-merlin.ng)；[fancyss 固件环境与平台包说明](https://github.com/hq450/fancyss)

### 华硕 AX58U V1 和 V2 应该查哪个梅林版本？

RT-AX58U V1 在原版 Asuswrt-Merlin 支持表中，RT-AX58U V2 在 GNUton 支持列表中。硬件修订决定应查的固件分支，选下载资料时必须保留 V1、V2，不能把“AX58U”当作同一个设备。

来源：[Asuswrt-Merlin 官方支持设备表](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices)；[GNUton 构建与支持设备](https://github.com/gnuton/asuswrt-merlin.ng)

### 华硕 AC68U 现在还支持梅林吗？

原版 Asuswrt-Merlin 已把 RT-AC68U 的所有版本和硬件修订列入不再支持设备。GNUton 列出的 DSL-AC68U 是另一个完整型号，不能把它的支持声明转给 RT-AC68U；历史固件资料也应与当前维护状态分开阅读。

来源：[Asuswrt-Merlin 官方支持设备表](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices)；[GNUton 构建与支持设备](https://github.com/gnuton/asuswrt-merlin.ng)

### 路由器能刷梅林，就能装 fancyss 或 MerlinClash 吗？

梅林固件的设备支持与 fancyss、MerlinClash 的插件适配是两项判断。fancyss 项目另有固件环境、软件中心和平台包要求，MerlinClash 也有自己的说明；型号出现在固件表里，不能代替这些插件条件与实际运行结果。

来源：[Asuswrt-Merlin 官方支持设备表](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices)；[fancyss 固件环境与平台包说明](https://github.com/hq450/fancyss)；[MerlinClash 项目说明](https://github.com/rts600/MerlinClash/blob/main/README.md)

## 交给自己的 AI 继续处理

工程书包含资料、待确认设备信息、检查项和交付要求。

[I-Lang 工程书](https://fanqiang.guide/guides/asus-merlin.ilang)

[返回指南目录](https://fanqiang.guide/guides/index.html)
