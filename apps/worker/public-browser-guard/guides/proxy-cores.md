# Mihomo、sing-box 与 Xray：代理内核、客户端和 TUN 的关系

客户端提供管理界面，内核解释配置并处理流量。协议、规则、DNS 与 TUN 是不同层面的能力，选择时要核对对应项目及版本。

整理日期：2026-09-13。具体版本、平台与型号以所引来源为准。

原文：https://fanqiang.guide/guides/proxy-cores.html

## 客户端与内核不是同一层

Clash Verge Rev 项目说明使用 Mihomo；v2rayN 可以调用 Xray、sing-box 等内核。用户看到的管理界面与实际解释配置的程序可以来自不同项目。

- 下载客户端时，同时核对它包含或调用的内核。
- 阅读文档时，将界面操作与内核配置字段分开。
- 排查问题时给出双方版本，避免只报一个应用名称。

来源：[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Xray-core 项目](https://github.com/XTLS/Xray-core)

## 相同协议不等于相同配置文件

协议用于表达与服务器通信的方式；完整配置还可能包含监听入口、路由、DNS 和规则来源。两个内核都支持某协议，不代表它们接受相同的配置结构。

- Mihomo 的字段以其配置文档为准。
- sing-box 的 TUN 字段有明确的平台与版本条件。
- 跨内核迁移应检查字段语义及不支持项，而不是只替换程序名。

来源：[Mihomo 配置文档](https://wiki.metacubex.one/config/)；[sing-box TUN 配置文档](https://sing-box.sagernet.org/configuration/inbound/tun/)；[Xray-core 项目](https://github.com/XTLS/Xray-core)

## TUN 与 DNS、路由一起核对

TUN 涉及虚拟网络接口及流量路由。是否由它处理某个请求，要结合系统、权限、路由和 DNS 配置判断；勾选 TUN 不能单独证明所有流量都符合预期。

- 记录操作系统、内核版本和采用的入口方式。
- 把域名解析与路由选择分开检查。
- 已有其他代理、虚拟网络或自定义路由时，先列出现状。

来源：[sing-box TUN 配置文档](https://sing-box.sagernet.org/configuration/inbound/tun/)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

## 常见问题

### Xray、sing-box 和 Mihomo 的官方文档在哪里？

Xray 官方中文文档在 xtls.github.io，sing-box 官方文档在 sing-box.sagernet.org，Mihomo 配置文档在 wiki.metacubex.one。查内核字段时应使用对应项目的文档；客户端下载和界面说明则查客户端自己的项目。

来源：[Xray 官方中文文档](https://xtls.github.io/)；[sing-box 官方文档](https://sing-box.sagernet.org/)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)；[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)

### 客户端和代理内核有什么区别，版本需要一样吗？

v2rayN、Clash Verge Rev 等客户端提供配置管理界面，Xray、sing-box、Mihomo 等内核负责解释配置并处理流量。客户端与内核是不同组件，版本号无需相同；需要确认客户端调用哪种内核，以及配置是否适合该内核版本。

来源：[v2rayN 项目与下载入口](https://github.com/2dust/v2rayN)；[Clash Verge Rev 项目](https://github.com/clash-verge-rev/clash-verge-rev)；[Xray-core 项目](https://github.com/XTLS/Xray-core)；[sing-box 官方文档](https://sing-box.sagernet.org/)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

### Xray、sing-box 和 Mihomo 能共用一份配置吗？

Xray、sing-box 与 Mihomo 各有自己的配置结构，支持相同协议也不代表能共用完整配置。节点、监听入口、路由和 DNS 要按目标内核分别核对；换程序或改文件后缀不会完成这些字段的迁移。

来源：[Xray 官方中文文档](https://xtls.github.io/)；[sing-box 官方文档](https://sing-box.sagernet.org/)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

### TUN 模式是做什么的，开启后所有流量都会走代理吗？

TUN 通过虚拟网络接口参与流量处理，具体哪些请求进入代理还取决于系统、权限、路由和 DNS 配置。sing-box 与 Mihomo 的相关字段应按对应版本文档核对；开关显示已启用不能单独代表每个应用的流量都符合预期。

来源：[sing-box TUN 配置文档](https://sing-box.sagernet.org/configuration/inbound/tun/)；[Mihomo 配置文档](https://wiki.metacubex.one/config/)

## 交给自己的 AI 继续处理

工程书包含资料、待确认设备信息、检查项和交付要求。

[I-Lang 工程书](https://fanqiang.guide/guides/proxy-cores.ilang)

[返回指南目录](https://fanqiang.guide/guides/index.html)
