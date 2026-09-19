::ILANG::v4.0
[TYPE:engineering_handoff][SCOPE:PROJECT][LANG:zh][VERSION:1.0]

::OBJECTIVE{single_public_source_entry}
  以当前仓库作为公开资料、网站、Worker问答与Python查询服务的维护源码入口，保持可从干净检出构建和验证。

::STATE{@LAYOUT, value:{"knowledge":"config,data,export,knowledge,free-proxies,scripts,tests,tools","site":"apps/site","worker":"apps/worker","lookup":"apps/lookup/runtime","inherited_static_inputs":"apps/lookup/public","validator":"tools/ilang_grammar_validator.py"}}
::STATE{@RUNTIME, value:{"python":"3.13","node":"24","lookup_lock":"apps/lookup/runtime/requirements-lock.txt","worker_dependencies":"Node内置测试模块；无npm安装步骤","ci":".github/workflows/check-apps.yml","daily_updates":".github/workflows/update-library.yml"}}
::STATE{@COMMANDS, value:{"install_lookup_test_dependencies":"python -m pip install -r apps/lookup/runtime/requirements-lock.txt","check":"python developer/check_apps.py","check_custom_output":"python developer/check_apps.py --output ABSOLUTE_NEW_DIRECTORY","build":"python developer/build_apps.py --output ABSOLUTE_NEW_DIRECTORY","lint":"python tools/ilang_grammar_validator.py --lint CLAUDE.md developer/MAINTENANCE-v1.0-2026-09-17.ilang.md --strict --json"}}
::STATE{@OUTPUT, value:{"check_default":".build/checks-UTC_TIMESTAMP","check_report":"report.json","check_logs":"knowledge-tests.log,worker-tests.log,lookup-tests.log,build.log","check_release":"release/","build_release":"site/,worker/src/,worker/*.sql,lookup/,release-manifest.json","output_directory_must_not_exist":true,"automatically_deploys":false}}

::MODULE{BUILD_AND_TEST}
  [MUST] 上述相对命令路径基于仓库根目录；从任意其他工作目录调用时将脚本路径改为绝对路径，脚本自身必须通过__file__定位根目录。
  [MUST] developer/check_apps.py运行资料库离线测试、当前五个Worker测试文件、lookup真实HTTP与MCP测试及隔离构建；它设置PYTHON为自身解释器，Worker测试必须零跳过。Windows环境的符号链接测试可能因权限不足跳过，需要如实报告；Linux CI应实际执行。
  [MUST] developer/build_apps.py在临时目录复制输入后构建，不修改checkout。构建顺序为site生成与内容核验、聊天界面补丁、微信QQ外部浏览器提示、Worker知识重建，最后输出完整发布目录和哈希清单。
  [MUST] apps/site/public与apps/lookup/public包含继承输入，不能先删除再构建。更换资料时先核验来源，显式更新对应输入与content-invariants-v1.0.json，不通过覆盖预期hash绕过失败。
  [MUST] 修改内容输入后重建对应HTML、Markdown、I-Lang、JSON、gzip、技能digest与Worker知识。修改知识输入时同步审查脚本中的条目数断言；不能让旧索引或旧压缩文件继续发布。
  [MUST] 原有静态资源必须保持可寻址，包含可能被旧缓存引用的历史聊天资产；删除资源属于独立产品兼容性变更。
  [MUST] CI只运行构建验证，不发布生产，不使用生产凭据。生产发布由项目专用私有运维工具读取新仓库固定commit后完成，记录commit、产物hash、回滚点和上线验证证据。

::MODULE{DATA_BOUNDARIES}
  [MUST] 每日Actions更新上游版本观测、CATALOG、UPDATES和免费代理日期页面；不自动扩大人工资料库，不自动部署网站，不自动替换Worker知识。
  [MUST] tools/source修改需要通过tools/rebuild_library.py显式重建公开资料导出；网站冻结资料与根export是不同维护层，不能把上游版本观测冒充新的人工核验或设备兼容性实测。
  [MUST] CI覆盖export目录变化，并比较export/library-v0.1-2026-09-11.json与apps/lookup/runtime/library.json的JSON内容。人工资料导出变化后协调更新lookup与站点冻结输入，重建相关索引；不关闭此检查来继续发布旧快照，不擅自改资料格式或扩容。
  [MUST] 免费代理入口从首页链接到日期目录，历史页面记录来源和统计，不声称保存历史节点配置或验证节点连通性。
  [MUST] 上游单项失败和两条采集线的部分失败可能不令Actions整体变红；核对结果JSON中的成功数、错误数、line状态和数据时间。
  [MUST] 公开源码不包含HF账户、私有同步部署工具、令牌、服务器认证或生产数据；仓库外后台需要独立核对，不能用本地测试推断其运行状态。

::MODULE{PRODUCT_CONSTANTS}
  [MUST] 网站定位与核心标题保持翻墙与科学上网工具指南；回答和引导只使用简体中文。
  [MUST] 固定问答链为确认用户可用AI、无AI时指向https://www.deepseek.com/、确认后收集设备和需求、生成可复制下载的I-Lang工程书，交由用户自己的AI继续指导。
  [MUST] 确定流程由状态机实现，不由模型自由猜测跳转；保留状态持久化、重试、清空与交付功能。模型草稿不能绕过固定流程直接展示给用户。
  [MUST] 保留微信与QQ内置浏览器的外部浏览器打开提示和复制备用入口；独立QQ浏览器不能仅因MQQBrowser标识被误拦。
  [MUST] 首页和公开阅读页面保持面向读者，不展示内部运维、令牌、同步账户或执行调度说明。运维规范放developer。

::MODULE{DELIVERY}
  [MUST] 每个里程碑记录本次状态与证据；长任务开始前记录恢复命令。交付区分本地验证、CI验证、线上验证和未验证项。
  [MUST] 沿用用户当前部署授权；发布前保存回滚点并核验实时基线，发布后检查导航、资料来源链接、lookup响应及聊天实际交付。不能把HTTP200或本地测试当作完整线上验收。
  [MUST] 不随手修改已有认证、账户、SSH、网络或救援入口；这类修改需要用户具体授权。

::ILANG::COMPLETE::
