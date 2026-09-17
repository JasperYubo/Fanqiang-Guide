# 维护者文档：自动更新

本文件记录后台运行与数据维护方法。首页和阅读页面只展示工具、知识和相关版本信息，不放置调度、鉴权、构建和维护操作说明。

这个仓库使用 GitHub Actions 定时检查公开 GitHub 项目。无需购买知识库产品，无需用户提供外部 API Key，也不依赖自建服务器或运行中的个人电脑。

## 自动更新什么

- 已收录且有明确 GitHub 仓库地址的项目：仓库访问结果、归档/禁用标记、最近推送时间、GitHub 返回的最新正式 Release 及其发布日期。
- [完整分类目录](../CATALOG.md)：全部资料条目及对应的版本、仓库状态和原始资料卡。
- [自动检查报告](../UPDATES.md)：追踪覆盖范围、最后检查时间、失败项目及其上次成功观测值。

GitHub 最新正式 Release 不包含草稿或预发布版本；没有 Release 不代表没有版本或停止维护。项目是否归档只表示 GitHub 仓库自身的标记。

自动化不会安装上游程序、执行上游脚本或实测设备。仓库访问成功不能证明条目身份、软件质量、刷机可行性或插件兼容性。教程、人工核验状态和华硕型号支持声明仍以资料中标出的依据为准。

## 什么时候更新

- 每天计划在北京时间 **06:17** 运行一次（UTC 22:17）。GitHub 可能延迟调度。
- 修改更新脚本、来源配置、测试或本工作流时，主分支自动验证并检查一次。
- 需要立即检查时，进入 [Actions](https://github.com/JasperYubo/Fanqiang-Guide/actions/workflows/update-library.yml)，选择 **Run workflow**。

定时任务只在默认分支运行。公开仓库连续 60 天没有仓库活动时，GitHub 会停用定时工作流。本仓库会提交实际检查结果与检查日期；若长期运行失败或任务被停用，仍需在 Actions 中恢复。GitHub 调度属于尽力执行，不能保证永久无人干预。

## 数据如何维护

| 文件 | 角色 |
|---|---|
| `export/library-v0.1-2026-09-11.json` 及同日期资料卡 | 初始人工整理快照，保留原核验范围 |
| `config/upstream-repositories.json` | 条目与 GitHub 仓库的明确对应关系；每个条目恰好被映射或列入排除原因 |
| `data/upstream.json` | 自动更新的上游观测值，记录本次状态与上次成功时间 |
| `CATALOG.md`、`UPDATES.md` | 从初始资料、来源配置与自动观测值生成的阅读页面 |

同一个字段只在它所属的数据层更新。日期化 JSON、JSONL、SQLite 和 RAG 文件是历史快照，不会伪装成本次检查后的数据；查询最新仓库/版本信息请使用自动观测文件或分类目录。新增条目需要同时补充基础资料和映射，生成器会检查覆盖关系。

基础资料的原料和完整重建工具已放在 [tools/](../tools/README.md)。维护者修改原料后运行 `python tools/rebuild_library.py`，同步生成资料卡、结构化库、检索集和映射；它不属于每日发布步骤。原料或生成器变更会触发离线验证，测试只在临时目录重建，不自动发布基础快照。

仓库改名或转移时，程序只接受 GitHub 官方 API 同站内、限定仓库路径的重定向，最多跟随三次；报告保留原映射并显示 GitHub 返回的当前仓库地址。跨站地址、循环跳转和非仓库路径不会继续访问。自动跟踪地址变化仍不代表重新核验了项目内容。未成功获取的新状态不会覆盖上次成功的数据；页面会标明旧值的时间。404 表示本次无法公开访问，不自动判定项目已删除；单次连接失败也不会删除资料。

## 无需外部接入的原理

Actions 使用 GitHub 自动创建的临时 `GITHUB_TOKEN` 读取公开 API，并将指定的生成文件提交回本仓库。没有个人访问令牌、模型 Key、自定义 Secret 或服务器账号。机器人提交仅以 `github-actions[bot]` 署名。公开节点订阅文件由独立的匿名 HTTPS 请求读取，不携带该令牌。

采集有超时、重试和并发限制。`scripts/run_update_pipeline.py` 分别执行“工具版本采集＋目录生成”和“免费代理采集＋日期页生成”。每条线先复制已有状态到独立临时目录，再采集和生成；只有整条线成功，产物才进入临时发布工作树。某条线失败不会阻止另一条成功线发布，失败状态文件和部分页面也不会混入提交；两线都失败则明确失败、不提交。共同离线测试仍是执行前置条件。

发布使用普通 Git 推送，最多尝试 3 次。只有收到非快进拒绝且确认远端主分支前进，才进入重试：若只修改了根目录 `README.md`，普通 rebase 后重推；若来源配置、脚本、数据、日期页或其他文件变化，则在最新主分支建立新的工作树，重新通过离线测试和目录校验后，当场重新采集、生成并提交。日期索引依据新基线的完整日期文件集合重建，不使用 `-X theirs`，也不强制推送。新基线校验不通过、鉴权/分支规则拒绝或 3 次推送均被并发更新阻挡时，本次明确失败，不声称已发布。

更新 job 允许最多 90 分钟，为必要的重新校验与采集留出时间；正常运行只采集一轮。编排器自身限时 88 分钟，并在子进程和推送前检查取消状态。取消后不再发起发布，已被服务器接受的提交不会因随后取消而回滚。API 令牌仅传给 `update_upstream.py` 子进程；其他子进程不接收 `GITHUB_TOKEN`/`GH_TOKEN`，但保留 checkout 配置的 Git 认证环境。日志只输出固定状态与成功/失败结果，不回显子进程命令或认证信息。

更新与生成在同一次工作流中完成，不依赖机器人提交再次触发其他工作流。修改逻辑先运行离线测试，只有通过后才进入自动检查。

本阶段自动追踪现有清单，不会自动将搜索结果收录成推荐项目，也不会调用 AI 重写教程。

## 每日免费代理资料

来源定义在 `config/free-proxy-sources.json`。首批来源为 Pawdroid/Free-servers、free-nodes/v2rayfree、mahdibland/V2RayAggregator 和 monosans/proxy-list。采集器 `scripts/free_proxy_sources.py` 读取明确列出的公开订阅文件，检查格式并统计条目，将观察结果写入 `data/free-proxy-sources.json`。配置允许的格式是 Base64 URI、逐行 URI 及注明协议的纯代理地址列表。

抓取器仅访问属于配置仓库的 `raw.githubusercontent.com` 地址，不跟随重定向，不执行上游代码或连接代理。单文件上限 2 MiB，并发上限 3、单请求限时 15 秒、整次限时 5 分钟。公开节点只在内存中解析，不把原始凭证写入日志、状态文件或日报。格式检查、去重及数量均不代表连通性实测；不同来源之间没有合并去重。

`scripts/build_free_proxy_pages.py` 依据观察时间换算北京时间，生成 `free-proxies/YYYY-MM-DD.md`，并更新文件夹内按日期倒序的 `README.md`。总首页只保留到 `free-proxies/` 的固定入口，不每日改写。跨日保留已有文件，同日重跑更新同名页面。历史页面保存当日统计和出处，订阅链接仍指向来源的当前内容，不能作为历史节点配置快照。

来源失败时保留上次成功统计并标记失败；来源身份、地址或格式变更后，不沿用旧来源的数据。至少一个来源本次成功才会生成新日期页面；全部失败时不发布免费代理这条线，不把旧统计包装成今日成功结果，工具版本线仍可独立成功。程序、格式或数据异常造成采集或页面生成失败时，该线的所有临时产物均不进入提交，已有公开页面保持原样。

免费代理抓取、日期页面生成和原工具版本更新在同一次每日工作流中分别完成，再统一提交成功线的结果。手动运行以及相关程序/配置修改也可触发；不会每天重建新的 GitHub 仓库。

## 维护者手动验证

Python 3.13，仅使用标准库：

```sh
python -m unittest discover -s tests -v
python scripts/build_catalog.py
```

完整采集建议使用 Actions 中的 **Run workflow**，由 GitHub 提供 API 额度；无需在本机配置令牌。单个项目失败可查看 Actions 步骤摘要与自动检查报告。

## 官方说明

- [GitHub Actions 自动令牌](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)
- [定时工作流及其限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub 最新正式 Release 接口](https://docs.github.com/en/rest/releases/releases#get-the-latest-release)
- [GITHUB_TOKEN 的触发行为](https://docs.github.com/en/actions/concepts/security/github_token)
