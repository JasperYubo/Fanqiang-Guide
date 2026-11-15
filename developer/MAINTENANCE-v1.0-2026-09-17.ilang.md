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
  [MUST] 常规CI只运行构建验证，不使用生产凭据。按用户明确授权的LINUX_PRODUCT_SYNC例外，项目专用私有Linux维护器验证固定commit并发布主站后，才可精确dispatch对应Pages工作流；Pages工作流使用自身受限GitHub权限发布该commit的公开页面。记录commit、产物hash、回滚点和上线验证证据。

::MODULE{LINUX_PRODUCT_SYNC}
  [MUST] 用户已授权服务器助手、MCP及两站关联展示变更由Linux维护器自动构建、测试与同步发布；此机制不依赖用户电脑，不把普通每日上游观测、CATALOG、UPDATES或免费代理日期变化升级为自动部署触发。
  [MUST] 维护器以持久事务和排他锁串行处理固定source_sha，事务贯穿主站发布、Pages精确工作流及公共产物验收。重启后先恢复未完事务，不在旧Pages任务结果未确认时开始新的主站切换。
  [MUST] Pages仅接受workflow_dispatch；source_sha、sync_id、contract_sha256必填。使用完整commit检出并核对HEAD，同次重试保留sync_id；首次接管前先核对并收尾既有Pages发布任务，不取消无关业务任务。
  [MUST] 主站随发布目录输出data/site-release.json及gzip，包含事务身份与实际安装器installer_sha256。Pages构建后和部署前分别核对主站产品合同、事务身份与安装器hash；身份不同的旧任务不得发布。
  [MUST] Pages输出deployment.json，记录实际source_sha、sync_id、contract_sha256、installer_sha256、run_id、run_attempt和index_sha256。不能把workflow事件head_sha当作实际检出源码；确认精确run成功后，还要读取公共Pages收据与HTML、主站安装器并核对实际字节。
  [MUST] 发布前保存实时基线和回滚点；保留现网资料、freshness状态、定时器和未涉及内容。失败时按已有授权进行有界重试、重新生成或恢复已验证版本，不绕过检查，不擅自修改认证或扩大业务范围。
  [MUST] 故障与恢复写入私有证据；成功通知以两站和MCP实际验收为条件。需要外部决策或凭据时明确报告具体阻塞，不声称已自动修复。

::MODULE{AUTOMATIC_RELEASE}
  [MUST] 每次产品更新由 Linux 完成构建、测试及双站发布后，Pages 工作流的独立 release job 自动生成 GitHub Release；不依赖维护者电脑开机。
  [MUST] Release 绑定完整 source_sha，标签为 release-加提交前12位；重新运行同一版本不得重复创建或覆盖已发布附件。
  [MUST] 每次正式 Release 前，Linux 隔离 Docker 执行候选安装器完整新安装，以及固定 1.0、1.1 和上一正式 Release 的升级；旧安装器绑定完整来源提交与 SHA256，覆盖角色不得缺失或跳过。
  [MUST] 新安装确认自动更新定时器已启用；升级前写入自定义节点配置、白名单、Key 与记忆，升级后逐字节与权限比较，核对 Xray 和 Nginx 进程未重启、服务健康、真实代理允许与拒绝通路正常。
  [MUST] 安装器及升级代码使用候选原始字节；仅 DeepSeek 账户校验与 ACME 签证使用隔离测试服务及测试 CA。测试不使用客户 Key，不把外部服务夹具当作生产账户或公网签证实测。
  [MUST] linux-install-upgrade-proof.json 绑定 source_sha、installer_sha256、工作流 run_id 和 run_attempt，并记录基线来源、结果及测试范围。缺少报告、失败、跳过或身份不匹配必须阻止正式发布，不得使用历史静态报告代替本次执行。
  [MUST] 报告作为公开 Release 附件，仅包含身份、摘要、测试项与结果，不包含 Key、节点内容或私有配置；在草稿转为正式 Release 前再次验证，只有通过版本进入客户自动更新渠道。
  [MUST] 发布前核对主站与 Pages 的事务身份、产品合同和实际安装器、Pages HTML 哈希；附件先上传到草稿并逐项校验，全部通过后正式发布。
  [MUST] 唯一既有回滚基线 270c81ba257398004ecf992d2cde2d3029d981de 不具有自动发版脚本，允许该精确版本只恢复页面。其他版本缺少脚本或校验失败必须报错，不能默认跳过。
  [MUST] Git 作者和提交者姓名均为 fanqiang guide，邮箱均为 info@fanqiang.guide；推送账户与提交署名分开核对。

::MODULE{CLIENT_ASSISTANT_UPDATES}
  [MUST] 客户 VPS 使用 huarun-auto-update.timer 本机定时检查正式 GitHub Release；新安装默认开启，既有 1.0/1.1 仅一次迁移后开启，不声称可远程接管未安装更新器的机器。
  [MUST] 仅执行资产摘要、发布证明、主站与 Pages 版本以及实际安装器字节都一致的版本；拒绝降级，不接受自定义下载上游或在请求中发送 Key。
  [MUST] 更新事务使用独占锁，聊天和本机管理使用共享锁；活动会话延期，继承描述符必须对应真实锁文件并重新确认排他锁，不能只信环境变量。
  [MUST] 保留节点配置、白名单、连接信息与 Key 原字节和权限，以及对话记忆；升级不重装或重启网络服务，不要求 Key 在线有效。变更前备份，持久事务恢复后再继续更新；健康退化或保护文件变化时回滚。
  [MUST] 自动更新尊重管理员停用设置，失败的相同发布暂缓 24 小时；状态查询不联网，不把终端管理员的启停权限授予模型。

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
