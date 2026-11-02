# Linux 私有报告收集端

收集端要求 Node.js 24，使用内置 node:sqlite，无需安装 npm 依赖。只保存严格结构化的测量报告，不接受原始日志、脱敏日志、IP、订阅地址或自由文本。报告没有公开读取或列表接口，不接入 GA4。

## 启动与部署

以独立非 root 用户 fanqiang-diag 运行编译后的 /opt/fanqiang-diagnostics/current/collector.mjs，Node.js 24 路径为 /opt/fanqiang-diagnostics/runtime/node-v24.18.1-linux-x64/bin/node。进程只允许监听 loopback；默认 127.0.0.1:8792。示例服务文件位于 deploy/collector.service.example，部署时须核对实际 Node.js 24 路径和安装目录。

环境变量：FQDIAG_HOST、FQDIAG_PORT、FQDIAG_DATA_DIR。数据目录默认 /var/lib/fanqiang-diagnostics，目录权限 0700，SQLite 与 collector.key 权限 0600。服务自行生成并持久化 32 字节 HMAC key；保留该文件，否则重试回执无法重现原删除令牌。备份需私有存储，不进入公开仓库、网站或日志。

反向代理在 /diagnostics-api/ 去掉前缀，转发到 http://127.0.0.1:8792/。只在该 location 为经过核实的 Cloudflare 网段还原客户端地址，然后覆盖 X-Diagnostics-Client 为 $remote_addr，不要透传用户提供的同名头。收集端只信任来自 loopback 的该头，地址只用于内存中的 HMAC 限流键，不写入数据库或应用日志。该 location 设置 access_log off、gzip off、client_max_body_size 64k、proxy_request_buffering off、proxy_buffering off，禁用缓存；其他站点入口保持现状。

## API 与数据边界

- GET /health 和 GET /v1/ping 返回小型 JSON。
- GET /v1/download?bytes=N 返回 1 字节至 10 MiB 随机数据，最长 15 秒。响应携带 no-store, no-transform、准确的 Content-Length 和 identity 编码。
- POST /v1/reports 只接受合同中的 {report,idempotency_key,consent}。idempotency_key 使用 UUID；consent 必须为 version=1、action=submit，以及预览报告 canonical SHA-256。首次成功返回 201，重复相同请求返回 200 和同一回执、删除令牌；同 key 不同内容返回 409。
- DELETE /v1/reports/:receipt_id 要求 Authorization: Bearer delete_token。成功返回 200 与 {"deleted":true}，并同时删除幂等关联。没有公开 GET 报告、导出或列表接口。

删除令牌由持久 HMAC key 和回执信息派生，数据库仅存令牌 hash。服务校验的是格式和用户提交的预览摘要，不能证明测量真实性。应用不提供 MCP 上传工具，也不会自行提交报告。

## 限额与保留

报告自接收起保留 30 天，进程每分钟清理；写入和删除时也清理到期数据。默认最多 10,000 份报告、64 MiB 报告正文、128 MiB SQLite 页面空间。SQLite 使用 secure_delete，过期或删除后报告及其幂等关联一起移除。文件可复用已释放页面，文件大小不会立即缩小。

请求正文上限 64 KiB，正文超时 5 秒；总请求并发 32、每地址并发 4；每分钟每地址 120 次、全局 600 次；每地址每小时新报告 20 份。幂等重试不消耗新报告限额。

下载并发为每地址 1、全局 2，每地址每小时最多 60 MiB、全局每小时最多 512 MiB。接收下载时预留整个请求额度，取消不返还额度，防止反复中断绕过流量限额。限流状态只在内存中保存，服务重启会重置；生产代理还应限制连接和请求速率。拒绝响应给出固定错误码和必要的 Retry-After，不回显输入。

## 本机导出与测试

站主可在服务器以数据目录所属用户运行 FQDIAG_DATA_DIR=/var/lib/fanqiang-diagnostics /opt/fanqiang-diagnostics/runtime/node-v24.18.1-linux-x64/bin/node /opt/fanqiang-diagnostics/current/collector.mjs export。输出为 NDJSON，只包含尚未过期的报告、回执号和接收/到期时间；不包含删除令牌或内部 hash。重定向的交付文件也应保持 0600，按实际授权保管。

在包目录运行 node --test test/collector*.test.mjs。测试使用临时目录和随机 loopback 端口，覆盖预览摘要、幂等重试/重启、恶意字段拒绝、删除、到期清理、容量、限流、慢请求、下载预算/取消/超时和本机导出；不调用生产接口。
