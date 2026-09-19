# 免费节点与订阅来源：Clash、V2Ray 和每日日期归档

每日资料通过固定文件夹进入，再选择日期文件。先辨认节点、订阅和 HTTP/SOCKS 代理的格式；资料收录与解析结果不等于连接可用性。

整理日期：2026-09-19。具体版本、平台与型号以所引来源为准。

原文：https://fanqiang.guide/guides/free-nodes.html

## 每日资料从哪里看

打开“按日期查看免费代理与节点资料”文件夹，按文件名选择日期。页面记录的是当日收录的来源与检查结果，便于对照不同日期的资料。

- 首页使用固定文件夹入口，无须记住每天的文件名。
- 阅读日期页中的来源项目、资料格式和核对说明。
- 历史页里的上游链接可能继续更新；日期页不等于当时所有原始节点的完整备份。

来源：[按日期查看免费代理与节点资料](https://github.com/JasperYubo/Fanqiang-Guide/tree/main/free-proxies)

## 节点、订阅和普通代理列表怎样区分

单个分享 URI 描述一个服务器配置；订阅地址指向客户端可以读取的配置集合。HTTP 或 SOCKS 的地址与端口列表又是另一类输入，不能只凭“免费代理”四个字互相替代。

- 通用 Base64 节点列表、Clash YAML 和 JSON 配置不是同一种格式。
- Shadowsocks SIP002 定义单节点分享链接，SIP008 则定义含服务器数组的在线 JSON 配置。
- 目标客户端是否支持该格式，必须结合版本和文档确认。

来源：[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[按日期查看免费代理与节点资料](https://github.com/JasperYubo/Fanqiang-Guide/tree/main/free-proxies)

## 日期新、条目多，分别说明什么

日期说明资料的收录或检查时间；条目数说明按页面规则解析到的数量。它们都不能直接回答某个节点在你的网络里能否连接、速度如何或能持续多久。

- 不同来源可能有重复项目，数量不能直接视为独立服务器总数。
- 页面标注的格式解析和来源访问检查，与用户端连接测试应分别阅读。
- 免费来源也可能变更内容；使用前由自己的 AI 核对来源、格式和必要参数。

来源：[按日期查看免费代理与节点资料](https://github.com/JasperYubo/Fanqiang-Guide/tree/main/free-proxies)

## 常见问题

### Clash 和 V2Ray 免费节点在哪里按日期找？

Fanqiang Guide 的 free-proxies 文件夹按日期提供免费代理与节点来源记录。选择日期文件，可以查看当日收录的来源项目、资料格式和检查记录，再按客户端需要辨认节点列表、Clash YAML 或其他配置。

来源：[按日期查看免费代理与节点资料](https://github.com/JasperYubo/Fanqiang-Guide/tree/main/free-proxies)

### 免费节点、订阅地址和 HTTP/SOCKS 代理列表有什么区别？

单节点分享链接描述一份服务器配置，订阅地址用于读取一组配置，HTTP/SOCKS 列表则通常记录代理地址与端口。例如 Shadowsocks 的 SIP002 定义单节点分享链接，SIP008 定义在线 JSON 服务器列表；选择资料时要匹配客户端实际接受的格式。

来源：[Shadowsocks SIP002 分享链接规范](https://shadowsocks.org/doc/sip002.html)；[Shadowsocks SIP008 在线配置规范](https://shadowsocks.org/doc/sip008.html)；[v2rayN 订阅与分享格式说明](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)；[按日期查看免费代理与节点资料](https://github.com/JasperYubo/Fanqiang-Guide/tree/main/free-proxies)

### 今天更新的免费节点，就代表现在都能用吗？

免费节点日期页记录的是资料收录或检查时间，节点数量记录的是页面所述规则下的解析结果。来源访问、格式解析与用户设备上的连接测试是不同结果；当前网络能否连接、速度与稳定性，需要相应实测证据。

来源：[按日期查看免费代理与节点资料](https://github.com/JasperYubo/Fanqiang-Guide/tree/main/free-proxies)

### 以前日期的节点页面，是当时全部节点的备份吗？

Fanqiang Guide 的历史日期页保留当日来源与检查记录，不等于全部原始节点内容的备份。日期页引用的上游链接可能继续更新，因此回看旧日期时，应区分当日记录和链接当前返回的内容。

来源：[按日期查看免费代理与节点资料](https://github.com/JasperYubo/Fanqiang-Guide/tree/main/free-proxies)

## 交给自己的 AI 继续处理

工程书包含资料、待确认设备信息、检查项和交付要求。

[I-Lang 工程书](https://fanqiang.guide/guides/free-nodes.ilang)

[返回指南目录](https://fanqiang.guide/guides/index.html)
