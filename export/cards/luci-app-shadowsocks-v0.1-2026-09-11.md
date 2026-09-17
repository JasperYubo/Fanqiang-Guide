# LuCI for Shadowsocks-libev

条目 ID：luci-app-shadowsocks  
类型：路由器插件  
资料状态：已读第一方资料  
记录日期：2026-09-11

为 OpenWrt 的 Shadowsocks-libev 提供透明代理、SOCKS5 和端口转发配置界面。

别名线索：luci-app-shadowsocks
平台线索（具体范围见核验说明）：Router
生态线索（具体范围见核验说明）：OpenWrt

## 核验范围

已阅读官方仓库简介、运行依赖与可执行文件对应表。


价格、版本、热度等来源快照保留在结构化数据的 source_claims/source_claim_sets 中，未自动提升为已核验结论。

## 兼容性

README 依赖 iptables/ipset 等；功能按实际安装可执行文件启用，当前 firewall4 兼容未核实。
具体支持型号：待核验

## 项目关系

- uses_core → [shadowsocks-libev](shadowsocks-libev-v0.1-2026-09-11.md)；关系状态：已读第一方资料；[依据](https://github.com/shadowsocks/luci-app-shadowsocks)

## 来源

- [来源 1 · github.com](https://github.com/shadowsocks/luci-app-shadowsocks)
