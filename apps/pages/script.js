"use strict";

(() => {
  const button = document.getElementById("copy-mcp");
  const address = document.getElementById("mcp-address");
  const status = document.getElementById("copy-status");
  if (!button || !address || !status) return;

  button.hidden = false;
  button.addEventListener("click", async () => {
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(address.value);
      status.textContent = "已复制完整 MCP 地址，可粘贴到你的 AI 客户端。";
      button.textContent = "已复制";
    } catch (_) {
      address.focus();
      address.select();
      address.setSelectionRange(0, address.value.length);
      status.textContent = "自动复制未成功，已选中完整地址。请使用复制快捷键或长按复制。";
      button.textContent = "重试复制";
    }
  });
})();
