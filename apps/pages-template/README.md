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

主站构建同时生成 `/data/product-contract.json`。Pages 发布工作流在部署前读取主站该合同，只有关键事实一致才发布；网络错误或事实不同会保留现有 Pages。
共享事实变更应先部署主站，再运行或重试 Pages 发布工作流。单纯样式、文案变更不需要更改 MCP 或工程书。
