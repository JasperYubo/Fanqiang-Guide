# 华硕路由器与梅林：先分清固件、软件中心和插件

查找华硕路由器资料时，你可能会遇到 Merlin、GNUton、Entware、fancyss、MerlinClash 等名字。它们负责的事情不同：有的是路由器系统，有的是安装软件的环境，还有的是具体插件。先分清这些关系，再对照自己的完整型号和固件版本，后面的资料会更容易看懂。

本文根据项目说明整理，资料核对日期为 **2026-09-11**；具体刷机和插件兼容情况仍需查看对应项目与版本的说明。

## ASUSWRT、原版梅林和 GNUton 有什么关系？

| 名称 | 它是什么 | 阅读资料时要分清什么 |
| --- | --- | --- |
| ASUSWRT | 华硕的固件体系 | 路由器的系统与后来安装的插件是两回事 |
| Asuswrt-Merlin（原版梅林） | 在 ASUSWRT 基础上开发的固件 | 有自己的支持机型，并可通过用户脚本、Entware、amtm 扩展能力 |
| GNUton 分支 | 重点提供额外机型支持的梅林分支 | 支持清单与原版梅林不同，要看完整型号和硬件版本 |
| KoolCenter 官改／梅改 | 华硕固件生态中的不同改版项目 | 需要区分具体项目；其中梅改在原版 Merlin 上加入软件中心所需的组件 |

因此，搜索“梅林下载”之后，还需要确定自己要找的是哪个项目、哪个机型对应的版本。原版梅林、GNUton 和梅林改版的名称不能混用。[Merlin 项目说明](https://github.com/RMerl/asuswrt-merlin.ng/wiki/About-Asuswrt)、[GNUton 项目](https://github.com/gnuton/asuswrt-merlin.ng)、[KoolCenter 梅改发布说明](https://www.koolcenter.com/t/topic/5072/1)。

## 软件中心、插件和核心分别做什么？

**先有固件及相应扩展环境，再看具体插件的要求。** 固件名称里有“Merlin”，并不表示已经安装透明代理；能看到软件中心，也不等于所有插件都适用于当前设备。

| 名称 | 作用与关系 |
| --- | --- |
| Entware | 软件包环境 |
| amtm | 在终端中管理脚本的菜单 |
| KoolCenter 软件中心／KoolShare rogsoft | 华硕改版固件相关的软件中心与插件项目，与 Entware、amtm 分别属于不同项目 |
| fancyss | 面向带软件中心的 ASUSWRT／梅林衍生固件的插件 |
| MerlinClash | 使用 Mihomo 核心的插件 |
| Mihomo、sing-box、Xray | 处理代理流量的核心程序；插件与核心需要分别辨认 |

例如，MerlinClash 是插件名称，Mihomo 是它使用的核心名称；判断是否适用时，需要分别查看固件环境、插件要求和具体版本。[fancyss 项目说明](https://github.com/hq450/fancyss)、[MerlinClash 项目说明](https://github.com/rts600/MerlinClash/blob/main/README.md)。

梅林的扩展功能还包括 DNS、VPN、访客网络和监控等。原版 Merlin Wiki 列出了相关脚本；Entware、amtm 和软件中心各有自己的说明入口。[amtm Wiki](https://github.com/RMerl/asuswrt-merlin.ng/wiki/AMTM)、[Entware](https://github.com/Entware/Entware)、[KoolShare rogsoft](https://github.com/koolshare/rogsoft)。

## 型号名字很接近，为什么还要分别查看？

完整型号、V1／V2 等硬件版本、固件分支及具体版本，都会影响你应当阅读哪份说明。原版 Merlin 与 GNUton 的两份支持清单中，共整理了 **58 条型号支持记录：39 条列入支持清单，19 条明确不再支持**。这些是项目的支持声明，尚未逐项验证刷机结果、发布包或插件兼容情况。

下面几组名称尤其容易混淆：

| 型号或组合 | 项目说明中的区别 | 需要继续核对的内容 |
| --- | --- | --- |
| RT-AX58U V1 | 原版 Merlin 支持设备页列出 V1 | 硬件标识、对应发布包和固件分支 |
| RT-AX58U V2 | GNUton README 列出 V2 | V1 与 V2 的固件不能混用 |
| RT-AX82U V1／V2 | GNUton README 分列两种硬件版本 | 两种版本各自对应的发布包 |
| GT-BE98／GT-BE98_PRO | GNUton 列出 GT-BE98；原版 Merlin 列出 GT-BE98_PRO | 名称相近不能视为可以互换固件 |
| RT-AC68U | 原版 Merlin 页面列为不再支持 | 历史固件与其他分支的维护情况 |
| DSL-AC68U | GNUton 另列 DSL-AC68U | 不能与 RT-AC68U 混同 |
| RT-AX89X 与 fancyss | fancyss 说明芯片位宽与固件运行位宽可能不同 | 插件包要匹配固件实际运行架构（ABI） |

来源：[原版 Merlin 支持设备](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Supported-Devices)、[GNUton 型号分组](https://github.com/gnuton/asuswrt-merlin.ng)、[fancyss 平台与机型表](https://github.com/hq450/fancyss)。

[查看完整的华硕／梅林型号支持表](merlin-model-matrix-v0.1-2026-09-11.md)。表里没有出现某个型号，不等于已经确认不支持；固件支持某型号，也不能直接推导出某个插件兼容。

## OpenWrt 和梅林里的插件可以混着看吗？

**它们属于不同的固件生态。** OpenWrt 提供系统及软件包基础，LuCI 提供网页管理界面；ImmortalWrt、iStoreOS、Lean LEDE 等项目分别有自己的变更范围。OpenClash、PassWall／PassWall2、HomeProxy、Nikki 等则属于应用层。看到插件也使用 Mihomo 或 sing-box，并不能据此认为它适用于梅林固件。[OpenWrt](https://github.com/openwrt/openwrt)、[ImmortalWrt](https://github.com/immortalwrt/immortalwrt)、[iStoreOS](https://github.com/istoreos/istoreos)。

iStore 作者明确说明，软件中心能装上，并不代表其中所有插件需要的组件都已满足。Nikki 也明确列出了 OpenWrt、Linux 内核和 firewall4 的前置要求；阅读插件资料时，应先看这些适用条件。[iStore](https://github.com/linkease/istore)、[Nikki](https://github.com/nikkinikki-org/OpenWrt-nikki)。

路由器固件还包括 FreshTomato、Gargoyle、Padavan 和 GL.iNet 官方系统等，它们也各有型号及功能限制。可以从[路由器固件目录](../CATALOG.md#router-firmware)继续查找对应项目，再回到项目的型号支持和版本说明。
