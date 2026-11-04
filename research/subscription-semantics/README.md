# 代理订阅转换的语义保留与差异检查

本地检查器比较一份 SIP008 JSON 与一份人工提供的 sing-box Shadowsocks 出站 JSON，回答选定字段是否保留、经过已知等价变换、发生改变，或仍无法判断。它不下载订阅、不运行转换器，也不修改客户端。

这是一个有限支持域的研究实现。配置可解析、字段相等、客户端可导入和真实网络可用是不同结论。本工具只检查前两者中的已建模部分。

## 快速运行

在 Linux、Python 3.10 或更新版本运行，无第三方依赖：

```sh
cd research/subscription-semantics
python3 checker.py \
  --source fixtures/01-preserved/source.json \
  --target fixtures/01-preserved/target.json \
  --mapping fixtures/01-preserved/mapping.json
```

这组样本应返回 `projection-equivalent`。换用 `06-plugin-loss` 目录内的三份文件，会发现插件名和插件参数丢失；返回码 1 是发现差异的正常结果。

`--output 新文件路径` 将报告写入本地文件，文件必须不存在，且不能覆盖输入。默认报告输出到终端；报告只包含固定字段名、数组位置、状态和原因码，不输出服务器地址、节点名称、秘密值、输入摘要或未知扩展键名。

## 输入与支持范围

| 输入 | 当前支持 |
| --- | --- |
| 源文件 | SIP008 version 1；1–256 个服务器，UUID、备注、地址、整数端口、方法与秘密字段。 |
| 目标文件 | sing-box JSON 的 outbounds 数组；通过显式映射检查 Shadowsocks 出站。 |
| 映射 | `pairs` 列表中的 `source_id` 对 `target_tag`；必须一对一。 |
| 单文件限制 | UTF-8 JSON，最大 1 MiB；重复 JSON 键、NaN、Infinity 被拒绝。 |

映射由使用者明确提供，它不是转换器生成来源的证明。未映射源节点、额外目标节点、未建模字段和目标全局 DNS／路由配置均产生 `unknown`，不会被悄悄略过。

```json
{
  "pairs": [
    {
      "source_id": "00000000-0000-4000-8000-000000000001",
      "target_tag": "synthetic-ss"
    }
  ]
}
```

比较字段为协议、地址、端口、方法、秘密、插件名与插件参数；另记录节点映射和备注到标签的声明式重命名。地址只接受已审阅范围内的 ASCII DNS 大小写等价，以及无区域标识的 IP 地址文本等价。不会解析 DNS、推测 IDNA、去除末尾句点或把相似方法名当作别名。

## 状态与退出码

| 字段状态 | 含义 |
| --- | --- |
| `field-preserved` | 已比较的字段值和存在状态一致，不证明客户端支持或网络有效。 |
| `transformed` | 显式映射／标签重命名、IP 文本或 ASCII DNS 大小写、已知可选空字段等价。 |
| `changed` | 字段值、类型、协议改变，或目标缺少必需字段。变化可能是有意的，需复核。 |
| `unsupported` | 本适配器没有投影通道的流量统计，或源插件不在审阅文档列出的目标插件集合。具体原因会区分两者。 |
| `unknown` | 未映射节点、未建模扩展、全局策略或超出地址正规化范围。不能据此宣称已保留。 |

退出码 0：全部已比较结果为保留或许可变换，汇总为 `projection-equivalent`。退出码 1：发现改变／不支持，或存在未知；对应 `differences-detected`／`incomplete`。退出码 2：输入、映射或本地读写失败。

目标插件集合依据 2026-11-04 核对的 [sing-box 官方文档](https://sing-box.sagernet.org/configuration/outbound/shadowsocks/)：`obfs-local` 与 `v2ray-plugin`。这是一份注明日期的适配器规则，不是对所有未来版本的保证。源文件无插件时，plugin 与 plugin_opts 可为空或省略；启用插件时必须显式给出字符串 plugin_opts（允许空串）。密码只按原字符串在内存中比较；没有验证 AEAD-2022 密钥长度、方法可用性或插件参数运行效果。

## 合成案例与复现

`fixtures/cases.json` 定义 19 个手工编写的合成案例及预期结果；每例有独立的 source、target、mapping。它们不是任何第三方转换器的输出，秘密字符串明确标为 SYNTHETIC，使用示例域名和文档地址，工具不向其发起连接。

```sh
python3 -m unittest -v test_checker.py
python3 run_examples.py --output /tmp/subscription-semantics-new-run.json
```

首次 Linux 运行完成 19/19 例、19/19 项单元测试：5 例为 `projection-equivalent`，8 例为 `differences-detected`，6 例为 `incomplete`。这表示这些已声明样本符合预期，并非对真实订阅的准确率估计。

固定证据位于 [evidence/run-2026-11-04.json](evidence/run-2026-11-04.json)，包含运行环境、逐例结果、检查器／测试／样本 SHA-256。复跑请写新证据文件；代码或样本有变更时，应重新生成证据并更新论文数字。

## 使用边界与来源

本实现没有调用 Sub-Store、subconverter、sub-web 或 sing-box，也没有执行客户端完整配置校验、连接测速、DNS／路由验收。SIP008 本身不包含完整客户端策略，字段投影相等不能推出整份配置行为相等。扩展到其他协议和格式时，应先增加明确适配规则、反例和来源，而不是把未知字段删除。

直接格式依据：[SIP008](https://shadowsocks.org/doc/sip008.html)、[sing-box Shadowsocks 出站](https://sing-box.sagernet.org/configuration/outbound/shadowsocks/)、[RFC 8259](https://www.rfc-editor.org/info/rfc8259/)。正规化依据：[RFC 4343](https://www.rfc-editor.org/info/rfc4343/)、[RFC 5952](https://www.rfc-editor.org/info/rfc5952/)。

许可：MIT。
