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

(() => {
  const button = document.getElementById("copy-install");
  const command = document.getElementById("install-command");
  const status = document.getElementById("install-copy-status");
  if (!button || !command || !status) return;
  button.hidden = false;
  button.addEventListener("click", async () => {
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(command.textContent);
      status.textContent = "已复制完整安装命令，请粘贴到你自己的 VPS 终端。";
      button.textContent = "已复制";
    } catch (_) {
      command.focus();
      const selection = window.getSelection();
      if (selection) {
        const range = document.createRange();
        range.selectNodeContents(command);
        selection.removeAllRanges();
        selection.addRange(range);
      }
      status.textContent = "自动复制未成功。请复制上方完整命令，再粘贴到自己的 VPS 终端。";
      button.textContent = "重试复制";
    }
  });
})();
