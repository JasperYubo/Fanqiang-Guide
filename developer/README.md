# 开发与维护索引

[仓库首页](../README.md) · [官网](https://fanqiang.guide/) · [AI 接入](https://fanqiang.guide/ai/)

本页指向当前实现与维护入口。运行状态和来源更新时间请读取公开接口；日期化交接文件保留它们各自版本的设计与验证记录。

## 当前服务与工程书

| 入口 | 当前内容 | 实现或资料 |
| --- | --- | --- |
| 公共 MCP | 2.6.0；`search`、`get`、`query`、`get_server_setup` | [服务声明](../apps/lookup/runtime/server-card.json) · [接口实现](../apps/lookup/runtime/app.py) |
| 设备配置工程书 | autosetup 2.1 | [正文](../apps/lookup/runtime/books/fanqiang-autosetup-v2.1.ilang.md) · [验证范围](../apps/lookup/runtime/books/fanqiang-autosetup-v2.1.evidence.json) |
| 梅林路由器工程书 | merlin 1.0 | [正文](../apps/lookup/runtime/books/fanqiang-merlin-v1.0.ilang.md) · [验证范围](../apps/lookup/runtime/books/fanqiang-merlin-v1.0.evidence.json) |
| 服务器安装工程书 | server 1.4；固定域名、TLS、厂商官方 API 自动发现与对接、通知和链式出口 | [正文](../apps/lookup/runtime/books/fanqiang-server-v1.4.ilang.md) · [助手实现](../apps/server/README.md) |
| 服务器排障工程书 | troubleshooting 1.0；通过 MCP 资源直接读取 | [正文](../apps/lookup/runtime/books/fanqiang-troubleshooting-v1.0.ilang.md) |
| 工程书注册与完整性 | 版本、资源 URI、摘要和验证元数据 | [统一注册表](../apps/lookup/runtime/setup_book.py) · [公开工程书目录](https://fanqiang.guide/api/agent/books) |
| HTTP 查询 | 搜索、条目、条件筛选、工程书与时效 | [OpenAPI](../apps/lookup/runtime/openapi.json) |

MCP 工程书资源为 `fanqiang://books/autosetup`、`fanqiang://books/merlin`、`fanqiang://books/server` 和 `fanqiang://books/troubleshooting`。`get_setup_book` 与 `/api/agent/setup-book` 保留兼容用途；新接入使用工程书资源或 `/api/agent/books`。服务读取公共资料，目标设备操作由用户自己的 AI 在已授权范围内执行。

## 修改哪一层

网站的用户、能力与边界见[产品约定](../PRODUCT.md)，页面结构、颜色与排版见[设计约定](../DESIGN.md)。

| 要修改的内容 | 从这里开始 |
| --- | --- |
| 仓库首页与入口 | [README](../README.md)，手工维护，不由每日任务重写 |
| 基础知识、卡片和日期化导出 | [资料重建方法](../tools/README.md)，修改原料后重建 |
| 分类目录与版本页的呈现 | [目录生成器](../scripts/build_catalog.py)，同步生成 `CATALOG.md`、`UPDATES.md` |
| 上游版本观察与免费代理资料 | [自动更新说明](../.github/maintenance-v0.1-2026-09-12.md) · [更新编排](../scripts/run_update_pipeline.py) |
| 网站和查询服务构建 | [应用构建](build_apps.py) · [应用检查](check_apps.py) |
| 来源更新时间 | [时效投影](refresh_knowledge_sources.py) · [时效同步](sync_source_freshness.py) · [公开状态](https://fanqiang.guide/api/agent/freshness) |
| 路由器上游变更观察 | [观察范围与复核流程](ROUTER_UPSTREAM_WATCH.md) · [每日工作流](../.github/workflows/check-router-upstream.yml) |
| 路由器型号与包匹配 | [兼容资料更新](update_router_compatibility.py) · [匹配数据](../data/router-compatibility.json) · [匹配逻辑](../apps/lookup/runtime/router_matching.py) |
| 服务器助手与 iLang 模板 | [助手源码](../apps/server/assistant/) · [安装器同步](sync_server_assistant.py) |
| 双站一致与自动发版 | Linux 同步维护触发 [Pages 工作流](../.github/workflows/pages.yml)；[安装与升级验收](server_release_e2e.py)通过后，[发布脚本](publish_github_release.py)核验报告、双站收据与附件，再生成正式 Release |
| 本地网络诊断工具 | [使用与开发说明](../apps/diagnostics/README.md) |

[原始知识库](../export/library-v0.1-2026-09-11.json)包含 310 条知识记录；[当前路由器资料](../data/router-compatibility.json)包含 56 行兼容匹配；[历史型号表](../export/merlin-model-matrix-v0.1-2026-09-11.json)保留 58 条固件支持声明。它们的记录口径与证据范围分别维护。

## 检查与证据

目录变更可使用离线测试及已有观察数据生成，不需要采集新版本：

```sh
python -m unittest discover -s tests -p test_build_catalog.py -v
python scripts/build_catalog.py
```

涉及网站或查询服务时，使用 [check_apps.py](check_apps.py) 的完整构建检查。[MCP 验证](verify_mcp_v2_public.py)与[梅林接口验证](verify_merlin_public.py)检查服务行为；[隔离 Linux 流程验证](verify_autosetup_linux_flow.py)记录特定应用代理路径的实际结果。工程书验证、接口验证与物理设备测试分别报告，不能互相替代。

上游仓库与正式 Release 观察、免费代理来源格式统计沿用现有流程。独立的路由器观察工作流每日对照已审核基线检查 fancyss 与已记录的 KoolCenter 来源，变化保留为待人工复核；报告见 Actions 摘要及 `router-upstream-review` 产物。该工作流进入默认分支后生效，不自动更新兼容矩阵或已审核包的固定版本。路由器上游观察不会安装软件、重写教程或实测代理连通性。部署和后台运行使用既有 Linux 环境；私有部署记录、认证信息与设备秘密不进入公开仓库。


## 正式发版前的安装与升级验收

每次正式 Release 都在 Linux 的隔离 Docker 系统中执行候选安装器完整安装，并从固定的 1.0、1.1 和上一正式 Release 分别升级。旧安装器按完整提交与 SHA256 校验；相同基线可合并执行，覆盖角色不得缺失。测试脚本为 [server_release_e2e.py](server_release_e2e.py)，报告校验规则为 [release_acceptance.py](release_acceptance.py)。

新安装必须启用自动更新定时器；升级前写入自定义节点配置、白名单、Key 和记忆，升级后逐字节及权限核对，并验证 Xray、Nginx 进程未重启，服务健康且真实代理通路的允许、拒绝规则均正常。报告缺失、任一失败、跳过、源码或安装器摘要不一致，都阻止正式 Release 发布；现有用户继续使用已安装版本。

验收运行真实安装器、PicoClaw、Xray、Nginx 和升级代码。DeepSeek 账户校验与 ACME 签证使用隔离测试服务及测试 CA，不使用客户 Key，也不把这些结果当作生产账户余额或公网证书签发的验证。测试不修改候选安装器字节。正式发布仍需双站身份与实际安装器摘要一致。

通过报告作为 `linux-install-upgrade-proof.json` 附在 Release 中，记录完整 `source_sha`、`installer_sha256`、工作流 `run_id` / `run_attempt`、基线来源和每项结果；不公开 Key、节点内容或私有配置。发布脚本在转为正式 Release 前再次核对证据，失败版本不能进入客户端自动更新渠道。相同安装器摘要不会让已安装用户重复升级。

## 网络维护与出口对接

[网络维护 v1.3 工程交接](SERVER-NETWORK-v1.3-2026-11-18.ilang.md)定义 Full account and zone access 账户令牌、固定域名与 TLS、入站 IP 同步、通知、DigitalOcean、Hetzner、Vultr 与 AWS 弹性地址恢复及链式 TCP 出口的共同约定。当前版本增加不限厂商名称的官方文档发现与声明式适配，详见[通用厂商 v1.4 工程交接](SERVER-PROVIDER-DISCOVERY-v1.4-2026-11-18.ilang.md)。当前真实验收范围以 [v1.4 元数据](../apps/lookup/runtime/books/fanqiang-server-v1.4.evidence.json)为准。普通程序升级和显式域名迁移分别验收；旧工程书的字节与网址保留。

## 历史交接记录

- [自动配置 MCP v1.0 交接](AUTOSETUP-MCP-v1.0-2026-11-02.ilang.md)：记录当时 service 1.2.0 / book 1.1 的集成；当前版本以本页和工程书注册表为准。
- [维护交接 v1.0](MAINTENANCE-v1.0-2026-09-17.ilang.md)
- [诊断工具交接](DIAGNOSTICS-v0.1.ilang.md) · [诊断入口交接](DIAGNOSTICS-DISCOVERY-v0.1.ilang.md)
