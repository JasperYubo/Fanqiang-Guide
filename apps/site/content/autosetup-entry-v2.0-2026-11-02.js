/* A public-reference copy helper; never connects MCP or operates a device. */
(() => {
  "use strict";
  const MCP_URL = "https://fanqiang.guide/mcp";
  const REQUEST_PATH = "/ai/setup-request.ilang";
  const MAX_BYTES = 65536;
  let requestPromise;

  async function loadRequest() {
    if (!requestPromise) {
      requestPromise = (async () => {
        const controller = new AbortController();
        const deadline = window.setTimeout(() => controller.abort(), 10000);
        try {
        const response = await fetch(REQUEST_PATH, {
          method: "GET", credentials: "omit", redirect: "error", signal: controller.signal,
          cache: "no-cache", headers: { Accept: "text/plain" }
        });
        if (!response.ok || new URL(response.url).origin !== window.location.origin) {
          throw new Error("Request unavailable");
        }
        if (Number(response.headers.get("content-length")) > MAX_BYTES) {
          throw new Error("Request too large");
        }
        let raw;
        if (response.body) {
          const reader = response.body.getReader();
          const chunks = [];
          let size = 0;
          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              size += value.byteLength;
              if (size > MAX_BYTES) {
                await reader.cancel();
                throw new Error("Request too large");
              }
              chunks.push(value);
            }
          } finally {
            reader.releaseLock();
          }
          raw = new Uint8Array(size);
          let offset = 0;
          for (const chunk of chunks) {
            raw.set(chunk, offset);
            offset += chunk.byteLength;
          }
        } else {
          raw = new Uint8Array(await response.arrayBuffer());
          if (raw.byteLength > MAX_BYTES) throw new Error("Request too large");
        }
        const text = new TextDecoder("utf-8", { fatal: true }).decode(raw);
        if (!text.startsWith("::ILANG::v5.0") || !text.includes("fanqiang://books/autosetup") && text.includes("resources/list")) {
          throw new Error("Unexpected request content");
        }
        return text;
        } finally {
          window.clearTimeout(deadline);
        }
      })().catch((error) => {
        requestPromise = undefined;
        throw error;
      });
    }
    return requestPromise;
  }

  for (const card of document.querySelectorAll("[data-setup-entry]")) {
    const status = card.querySelector("[data-copy-status]");
    const fallback = card.querySelector("[data-setup-fallback]");
    const requestText = card.querySelector("[data-setup-request-text]");
    const mcpText = card.querySelector("[data-mcp-fallback]");
    if (mcpText) mcpText.value = MCP_URL;
    const say = (message) => { if (status) status.textContent = message; };
    const fillRequest = async () => {
      const text = await loadRequest();
      if (requestText) requestText.value = text;
      return text;
    };
    let skipProgrammaticOpen = false;
    const openFallback = () => {
      if (fallback && !fallback.open) {
        skipProgrammaticOpen = true;
        fallback.open = true;
      }
    };
    const showFallback = (element) => {
      openFallback();
      if (element) {
        element.focus();
        element.select();
      }
    };
    if (fallback) {
      fallback.addEventListener("toggle", () => {
        if (skipProgrammaticOpen) {
          skipProgrammaticOpen = false;
          return;
        }
        if (!fallback.open || (requestText && requestText.value)) return;
        fillRequest().catch(() => say("请求暂时无法加载。请使用下方“下载同一份配置请求”链接，或稍后重试。"));
      });
    }
    for (const button of card.querySelectorAll("[data-copy-mcp], [data-copy-setup-request]")) {
      button.addEventListener("click", async () => {
        const isRequest = button.hasAttribute("data-copy-setup-request");
        button.disabled = true;
        let text;
        try {
          if (isRequest) say("正在读取本站配置请求……");
          text = isRequest ? await fillRequest() : MCP_URL;
        } catch {
          openFallback();
          say("请求暂时无法加载。请使用下方下载链接，或稍后重试；没有连接 MCP 或执行配置。");
          button.disabled = false;
          return;
        }
        try {
          if (!navigator.clipboard || !window.isSecureContext) throw new Error("Clipboard unavailable");
          await navigator.clipboard.writeText(text);
          say(isRequest ? "配置请求已复制。粘贴给自己的 AI，并说明目标设备和需求。" : "MCP 地址已复制。在自己的 AI 中选择 Streamable HTTP；本站知识服务无需令牌。");
        } catch {
          showFallback(isRequest ? requestText : mcpText);
          say(isRequest ? "浏览器未允许自动复制。请求已展开并选中，请手动复制；也可下载同一份请求。" : "浏览器未允许自动复制。地址已展开并选中，请手动复制。");
        } finally {
          button.disabled = false;
        }
      });
    }
  }
})();
