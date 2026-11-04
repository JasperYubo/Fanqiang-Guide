# 引用与出版版本维护

本项目以一篇系统技术报告和五篇专题报告或技术说明记录华润（Fanqiang Guide）的核心方法。六篇是独立出版记录，分别管理正文、附件、版本与 DOI；公开网站入口为[研究成果](https://fanqiang.guide/research/)。

## 选择引用对象

- **华润（Fanqiang Guide）：面向 AI 设备配置的知识组织、执行协议与诊断体系**: 1.0 (2026-11-04), DOI [10.5281/zenodo.23961021](https://doi.org/10.5281/zenodo.23961021).
- **面向用户自主 AI 的设备配置协议：目标绑定、局部修复与证据验收**: 1.0 (2026-11-04), DOI [10.5281/zenodo.23961041](https://doi.org/10.5281/zenodo.23961041).
- **基于来源约束与未知状态的梅林路由器插件包匹配方法**: 1.0 (2026-11-04), DOI [10.5281/zenodo.23961043](https://doi.org/10.5281/zenodo.23961043).
- **本地网络诊断的有限测量与主动提交协议**: 1.0 (2026-11-04), DOI [10.5281/zenodo.23961045](https://doi.org/10.5281/zenodo.23961045).

- **代理订阅转换的语义保留与差异检查方法**: 1.0 (2026-11-04), DOI [10.5281/zenodo.23963553](https://doi.org/10.5281/zenodo.23963553).
- **旧手机共享网络的端到端配置与验收方法**: 1.0 (2026-11-04), DOI [10.5281/zenodo.23963555](https://doi.org/10.5281/zenodo.23963555).

讨论整体知识组织与系统职责时引用主报告；讨论设备流程、路由器选包或诊断披露时引用对应专题。复现实现时，另列实际使用的源码提交、工程书版本和必要环境。论文版本与网站持续更新的运行版本应分别记录。

首批四篇 1.0 版的基础源码为 `7bfc3e01e3fcea3866ac1b57e69f5461a2b1b250`，涉及 MCP 2.1.0、设备配置工程书 2.1、梅林工程书 1.0 与本地诊断 0.1.0。文档与接口校验、隔离 Linux 流程、包来源检查和真实硬件验收是不同证据：现有隔离流程不能替代手机热点或路由器的现场测试。引用具体结果时保留该篇的验证范围。

第二批订阅转换差异检查与共享网络验收报告的工具实现快照为 `8261a8b8e7a3189bc0eec8c23c7e7906d3f6f063`。配套源码、合成案例及运行证据分别位于 `research/subscription-semantics/` 和 `research/shared-network-validation/`；报告页面和 Zenodo 附件提供独立工具包。

## 文件职责

| 文件 | 用途 |
| --- | --- |
| `research/publications.json` | 六篇出版物的标题、摘要、正文、参考文献、作者、DOI、版本与对应源码。 |
| `CITATION.cff` | 按 CFF 1.2.0 描述仓库软件项目；`preferred-citation` 指向系统报告，`references` 列出六篇出版物。 |
| `.zenodo.json` | 仓库未来独立软件快照的归档元数据；通过 `isSupplementTo` 关联六篇出版物。 |
| 网站 `/research/` | 面向读者的全文、摘要、参考文献与下载入口。 |

技术出版物使用各自的记录元数据。仓库的 `.zenodo.json` 不替代这些记录，也不填写其中任何一篇的 DOI 作为软件 DOI。将来若另行归档软件，应绑定当时的源码、版本、日期与检查结果。

## 引用与作者身份

每个引用必须对应正文中的问题、方法或工程证据。平台行为引用官方平台文档，协议与算法引用标准，包选择引用固定上游源码或发行清单；相关研究放在相关工作中，说明与本文的联系及范围差异。优先使用准确的版本 DOI；没有 DOI 的官方材料保留可核验 URL，并记录访问日期或源码提交。

参考文献保留原作者和真实题名；只有经出版方或 DOI 元数据核实的 ORCID 才写入该参考文献的 `author_identifiers`。参考文献作者不进入本文的作者列表。当前六篇的作者为 Zhu, Long Quan，机构为 iLang Inc.，ORCID 为 [0009-0004-4540-8082](https://orcid.org/0009-0004-4540-8082)。

相关标识符按关系实际方向填写：`cites` 表示本作品引用目标作品；`isSupplementTo` 表示本作品是目标作品的补充；主报告与专题的关系以各自元数据为准。不要仅因题目相近或希望建立关联而加入与正文无关的文献。关系类型以 [DataCite 官方定义](https://datacite-metadata-schema.readthedocs.io/en/4.6/properties/relatedidentifier/)为准。

## 更新出版版本

1. 在 Linux 工作副本修改对应出版物正文、参考文献与版本信息，保持其他出版记录独立。
2. 检查正文引用编号、作者身份、DOI、来源版本和验证范围，重新生成受影响的论文附件与网站内容。
3. 使用 [Zenodo 公开 REST API](https://developers.zenodo.org/)管理记录：公开记录可通过 `/api/records/{id}` 读取；已发布内容需要新附件版本时，使用该记录的创建新版本流程，并遵循 API 返回的草稿链接。仅修正元数据时使用记录支持的编辑流程。
4. 发布后检查公开记录状态、文件清单和 DOI 元数据，再同步 `publications.json`、CFF 与网站。未发布的草稿和预留 DOI 不标作已完成发布。

认证凭据只供指定 Linux 发布环境使用，不写入源码、命令输出、论文附件或交付包。网站、上游检查和 DOI 发布各有独立生命周期；日常资料更新不应自动触发一批论文新版本。

## 未来软件自动归档

本次没有启用 GitHub–Zenodo 自动归档，也没有增加自动发布 DOI 的工作流。若以后启用，应在 Zenodo 为仓库单独开启集成，并在一个明确的软件 Release 上核对归档结果。仅添加元数据文件不会启用集成。

当仓库同时存在 `.zenodo.json` 与 `CITATION.cff` 时，Zenodo 的 GitHub 归档优先读取 `.zenodo.json`；GitHub 则使用 CFF 提供引用入口。两者必须分别维护，见 [Zenodo CFF 说明](https://help.zenodo.org/docs/github/describe-software/citation-file/)与[启用仓库说明](https://help.zenodo.org/docs/github/enable-repository/)。CFF 修改后按[官方 1.2.0 schema](https://github.com/citation-file-format/citation-file-format/blob/1.2.0/schema.json)校验。
