# 旧手机共享网络的端到端配置与验收方法

本目录是离线报告判定器，不安装软件、不读手机、不发请求、不上传报告。输入由操作者提供，程序不能认证证据真实性或证明全部手机适配。

## 运行

Python 3.10+，无第三方依赖，在本目录执行：

    python3 -B -m unittest -v test_validate_report.py
    python3 -B validate_report.py report-template.json
    python3 -B validate_report.py examples/synthetic-complete.json

退出码 0=声明范围通过，1=失败，2=未完成，3=无效输入。空模板返回 2。
合成完整案例返回 0，但 verification_scope=synthetic_logic_only，device_acceptance=not_tested。
CLI 仅输出结果，不自动保存或上传。

## 模型

上游 → 共享主机 → 明确机制/接口 → 下游设备 → 被测应用。
mode 为 explicit_proxy 或 gateway；热点链路不是代理路径。主机准备需要官方支持依据、实际接口观察和已知版本/上游。
core_version=not_exposed 仅指发行方没有单独公布核心版本，需已知客户端版本和支持证据。unknown 仍阻断通过。

每台下游至少一个具体应用，以 device-1、app-1 等假名绑定，真实映射留本地。
六通道为 dns_ipv4、dns_ipv6、tcp_ipv4、tcp_ipv6、udp_ipv4、udp_ipv6。
DNS 后缀是解析请求的传输族，TCP/UDP 后缀是业务目标族；AAAA 可经 IPv4 DNS 查询。
至少一个 DNS 路径在范围内；受控查询须覆盖实际目标 A/AAAA 及应用自身解析，细节由本地证据记录。

业务预期为 proxy/direct/blocked，DNS 为 proxy_resolver/approved_direct_resolver/blocked。
normal 与 baseline 分别声明正常和恢复原设置预期。
disconnect=block 或 allow_direct；sleep=maintain 或 block。直连是否失败取决于预先策略。
五阶段 normal、disconnected、reconnected、sleep、restored；每个应用 30 行加会话主机准备。
至少一个必需 TCP 通道的 normal 必须为 proxy 或 direct，其他通道可以预期阻断；全部正常业务均阻断不是访问验收成功。显式代理不自动免除必需 UDP 或其他应用检查。

## 状态

| 状态 | 含义 |
|---|---|
| pass | 方法和证据齐备，观察匹配预期 |
| fail | 充分观察与预期冲突，或热警告 |
| not_tested | 没执行，无虚构观察、时间和证据 |
| unknown | 证据不足、冲突、不支持或方法不足 |
| not_applicable | 测试前排除并保留范围依据 |

输入使用 observed 而非 pass，程序比较后产生 pass/fail。
必需项 not_applicable 转 unknown。不能事后删除未测项；范围外行也保留排除证据。
任一 fail 总结果 fail；否则有 unknown/not_tested 则 incomplete；全部所需通过才 pass。

DNS 要 controlled_dns_query + resolver_path_observation。
业务要 transport_probe + route_observation。
非正常阶段加 transition_observation；阻断加 working_control_probe。
exit_ip 只能辅助，单独不能证明任何通道或所有应用覆盖。
方法是操作者对本地取证的声明，程序不认证截图/数据包真实性。

conditions 记录休眠秒数、切换窗口、每格探测预算、数据预算、充电及热警告。
模板留空；合成案例的 600 秒是逻辑输入，不是手机实验记录。
真实检查保留控制/恢复路径；短时通过不认证全天稳定或持续充电安全。

## 脱敏模板

report-template.json 闭合字段仅需假名、受限版本、UTC 时间、枚举策略和观察。
不需要日志、SSID、MAC/IP、域名、订阅 URL、口令或浏览历史。
evidence-1 等引用对应本地遮盖秘密的截图/记录，原件和映射表留本地。
拒绝额外字段、URL 引用、重复 JSON 字段、非有限常量和过深结构；只读普通文件，最多 2 MB，错误不回显输入。
这不是任意文本脱敏器，不能把秘密伪装为版本等允许字段。公开前复核字段及关联风险。
离线判定不是上传授权，提交沿用本地预览和主动同意协议。

## 工程书映射

- HOTSPOT：拓扑、主机、机制、恢复基线，对应 topology、host_readiness、policy。
- VERIFY_SHARED：逐下游/应用矩阵、条件与证据；无实测保留 not_tested。
- MAINTAIN_SHARED：启停、清理代理、恢复及变更后另开会话重验。

23 个测试方法只验证数据结构与判定逻辑；4 个 examples 全为合成数据，未做手机或热点实验。
