# 共享网络验收工具

请先阅读 [方法、字段定义与运行步骤](METHOD.md)。

本工具在本地读取填写好的 JSON，检查声明的共享拓扑、六通道五阶段观察与预期策略。它不连接手机、不修改网络，也不上传报告。

- [待填写模板](report-template.json)
- [合成示例](examples/)
- [Linux 测试与案例结果](evidence/)

运行：`python3 validate_report.py report-template.json`。模板返回未完成属于预期行为；完整合成示例通过只代表逻辑通过，设备验收仍是未测。依赖 Python 3.10+，仅使用标准库。

复现测试：`python3 -B -m unittest -v test_validate_report.py`。
