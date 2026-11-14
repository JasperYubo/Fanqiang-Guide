# 项目入口模板

`index.html` 是 GitHub Pages 的源模板；发布文件是 `apps/pages/index.html`。
编辑布局和文字时保留 `{{...}}` 事实占位符。服务器助手、MCP 和工程书版本来自
`apps/site/product_contract.py`，该模块读取既有 MCP registry。

在 Linux 仓库目录生成并检查页面：

```sh
python developer/sync_pages_contract.py --write
python developer/sync_pages_contract.py --check
python developer/check_pages_seo.py
```

将模板与生成的页面一起提交。CSS、JavaScript 指纹由生成器读取实际文件计算，工程书卡片和数量按 registry 生成。

主站构建生成 `/data/product-contract.json`。Linux 维护器验证固定 commit，发布带 `/data/site-release.json` 收据的主站，再 dispatch 同一 `source_sha`、`sync_id`、`contract_sha256` 的 Pages 工作流。Pages 不再由 push 直接发布。

Pages 两次核对主站事务、产品合同和安装器 hash，部署产物带 `/deployment.json`。维护器确认精确工作流结果、公开收据及页面字节后才完成事务；同次恢复沿用原事务 ID。单纯样式、文案变更不需要更改 MCP 或工程书。
