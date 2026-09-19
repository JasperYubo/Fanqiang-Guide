/* Fanqiang Guide chat v1.0. No credential or conversation storage in the browser. */
(() => {
  "use strict";
  const MAX_INPUT = 1500;
  const MAX_OUTPUT = 160000;
  const form = document.getElementById("guide-query-form");
  if (!form || !window.fetch || !window.TextDecoder || !window.AbortController) return;
  const input = document.getElementById("site-query");
  const ask = document.getElementById("chat-ask");
  const panel = document.getElementById("chat-panel");
  const transcript = document.getElementById("chat-transcript");
  const status = document.getElementById("chat-status");
  const stop = document.getElementById("chat-stop");
  const reset = document.getElementById("chat-reset");
  const artifactButton = document.getElementById("chat-artifact");
  const counter = document.getElementById("chat-input-count");
  let sessionReady = false;
  let busy = false;
  let controller = null;
  let hasConversation = false;

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function setStatus(message, tone = "normal") {
    status.textContent = String(message || "").slice(0, 500);
    status.dataset.tone = tone;
  }

  function setBusy(value) {
    busy = value;
    ask.disabled = value;
    reset.disabled = value;
    artifactButton.disabled = value || !hasConversation;
    stop.hidden = !value;
    transcript.setAttribute("aria-busy", String(value));
  }

  function safeSourceURL(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" && !url.username && !url.password ? url.href : null;
    } catch (_) { return null; }
  }

  function safeArtifact(value) {
    if (!value || typeof value !== "object" || typeof value.url !== "string") return null;
    try {
      const url = new URL(value.url, window.location.origin);
      const match = /^\/api\/chat\/artifacts\/([A-Za-z0-9_-]{1,160})$/.exec(url.pathname);
      if (url.origin !== window.location.origin || url.username || url.password || url.search || url.hash || !match) return null;
      if (value.id && value.id !== match[1]) return null;
      const filename = String(value.filename || "fanqiang-guide.ilang.md").replace(/[\\/:*?"<>|\x00-\x1f]/g, "-").slice(0, 160);
      return { url: url.href, filename };
    } catch (_) { return null; }
  }

  function appendMessage(role, content = "") {
    const article = node("article", "chat-message chat-message-" + role);
    article.append(node("span", "chat-message-label", role === "user" ? "你" : "AI"));
    const body = node("div", "chat-message-body", content);
    article.append(body);
    transcript.append(article);
    return { article, body, sources: null, artifact: null };
  }

  function nearBottom() {
    return transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 90;
  }

  function scrollBottom(force = false) {
    if (force || nearBottom()) transcript.scrollTop = transcript.scrollHeight;
  }

  function renderSources(message, sources) {
    if (message.sources) message.sources.remove();
    message.sources = null;
    if (!Array.isArray(sources)) return;
    const wrapper = node("div", "chat-sources");
    wrapper.append(node("span", "chat-sources-label", "参考资料"));
    const list = node("ul");
    const seen = new Set();
    for (const source of sources.slice(0, 20)) {
      if (!source || typeof source.url !== "string") continue;
      const url = safeSourceURL(source.url);
      if (!url || seen.has(url)) continue;
      seen.add(url);
      const link = node("a", "", String(source.title || source.label || new URL(url).hostname).slice(0, 180));
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      const item = node("li");
      item.append(link);
      list.append(item);
    }
    if (seen.size) {
      wrapper.append(list);
      message.article.append(wrapper);
      message.sources = wrapper;
    }
  }

  function renderArtifact(message, artifact) {
    const safe = safeArtifact(artifact);
    if (!safe) throw new Error("工程书下载地址暂不可用，请重新生成。");
    if (message.artifact) message.artifact.remove();
    const card = node("div", "chat-artifact-card");
    card.append(node("span", "chat-artifact-name", safe.filename));
    const download = node("a", "", "下载工程书 ↓");
    download.href = safe.url;
    download.download = safe.filename;
    card.append(download);
    message.article.append(card);
    message.artifact = card;
  }

  async function postJSON(path, data, signal) {
    const response = await fetch(path, {
      method: "POST", credentials: "same-origin", cache: "no-store", signal,
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(data)
    });
    let payload;
    try { payload = await response.json(); }
    catch (_) { throw new Error("服务返回了无法读取的结果，请稍后重试。"); }
    if (!response.ok) throw new Error(typeof payload.message === "string" ? payload.message : "暂时无法连接 AI，请稍后重试。");
    return payload;
  }

  async function ensureSession(signal) {
    if (sessionReady) return;
    setStatus("正在打开对话…");
    const payload = await postJSON("/api/chat/session", {}, signal);
    if (payload.session !== true) throw new Error("对话暂时无法建立，请稍后重试。");
    transcript.replaceChildren();
    for (const saved of Array.isArray(payload.messages) ? payload.messages : []) {
      if (!saved || !["user", "assistant"].includes(saved.role)) continue;
      const text = typeof saved.content === "string" ? saved.content.slice(0, MAX_OUTPUT) : "";
      const isBook = saved.role === "assistant" && saved.artifact;
      const isBookRequest = saved.role === "user" && text.startsWith("::ILANG::v5.0") && text.includes("::MODULE{ARTIFACT_REQUEST}");
      const message = appendMessage(saved.role, isBook ? "工程书已生成，可以下载后交给你自己的 AI。" : isBookRequest ? "根据本次对话生成 I-Lang 工程书。" : text);
      renderSources(message, saved.sources);
      if (isBook) {
        try { renderArtifact(message, saved.artifact); }
        catch (_) { message.article.append(node("p", "chat-message-note", "原工程书下载地址不可用，可以重新生成。")); }
      }
      hasConversation = true;
    }
    sessionReady = true;
    scrollBottom(true);
  }

  // SSE lines may cross byte chunks; CRLF, comments, and multi-line data are supported.
  class SSEParser {
    constructor(onEvent) { this.onEvent = onEvent; this.buffer = ""; this.event = "message"; this.data = []; }
    line(value) {
      if (value === "") {
        if (this.data.length) this.onEvent(this.event, this.data.join("\n"));
        this.event = "message"; this.data = []; return;
      }
      if (value.startsWith(":")) return;
      const colon = value.indexOf(":");
      const field = colon < 0 ? value : value.slice(0, colon);
      let content = colon < 0 ? "" : value.slice(colon + 1);
      if (content.startsWith(" ")) content = content.slice(1);
      if (field === "event") this.event = content;
      if (field === "data") this.data.push(content);
    }
    push(chunk, final = false) {
      this.buffer += chunk;
      let end;
      while ((end = this.buffer.indexOf("\n")) >= 0) {
        this.line(this.buffer.slice(0, end).replace(/\r$/, ""));
        this.buffer = this.buffer.slice(end + 1);
      }
      if (this.buffer.length > MAX_OUTPUT) throw new Error("返回内容过长，请缩短问题后重试。");
      if (final && this.buffer) { this.line(this.buffer.replace(/\r$/, "")); this.buffer = ""; }
      if (final) this.line("");
    }
  }

  async function readAnswer(response, message, mode) {
    if (!response.body || !response.headers.get("Content-Type")?.includes("text/event-stream")) throw new Error("AI 返回格式不正确，请稍后重试。");
    let finished = false;
    let received = "";
    const parser = new SSEParser((event, raw) => {
      let data;
      try { data = JSON.parse(raw); } catch (_) { throw new Error("回答传输中断，请重新提问。"); }
      if (!data || typeof data !== "object") throw new Error("回答格式不正确，请重试。");
      const pinned = nearBottom();
      if (event === "status" && typeof data.message === "string") setStatus(data.message);
      if (event === "delta" && typeof data.text === "string") {
        received += data.text;
        if (received.length > MAX_OUTPUT) throw new Error("回答过长，已停止接收。");
        if (mode === "answer") message.body.textContent = received;
      }
      if (event === "sources") renderSources(message, data.sources);
      if (event === "artifact") {
        renderArtifact(message, data);
        message.body.textContent = "工程书已生成，可以下载后交给你自己的 AI。";
      }
      if (event === "error") throw new Error(typeof data.message === "string" ? data.message : "生成暂未完成，请重试。");
      if (event === "done") {
        if (data.ok !== true) throw new Error("回答尚未完成，请重试。");
        finished = true;
      }
      if (pinned) scrollBottom(true);
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        parser.push(decoder.decode(value, { stream: true }));
        if (finished) { await reader.cancel(); break; }
      }
      parser.push(decoder.decode(), true);
    } finally {
      if (!finished) { try { await reader.cancel(); } catch (_) { /* fetch may already be aborted */ } }
      reader.releaseLock();
    }
    if (!finished) throw new Error("连接中断，回答可能不完整。你可以继续追问。");
    if (mode === "artifact" && !message.artifact) throw new Error("工程书尚未生成，补充需求后可重试。");
    if (mode === "answer" && !received.trim() && !message.artifact) throw new Error("未收到完整回答，请重试。");
  }

  function artifactRequest(text) {
    return "::ILANG::v5.0\n[TYPE:request][PROJECT:fanqiang_guide]\n::MODULE{ARTIFACT_REQUEST}\n" +
      "::STATE{@USER_CONTEXT, value:" + JSON.stringify(text || "使用本次对话已明确的需求") + "}\n" +
      "[MUST] 基于当前对话与用户需求生成可下载的 I-Lang 工程书，供用户自己的 AI 继续处理。\n::ILANG::COMPLETE::";
  }

  async function send(mode = "answer") {
    if (busy) return;
    const text = input.value.trim();
    if (!text && mode === "answer") { input.focus(); return; }
    panel.hidden = false;
    if ([...text].length > MAX_INPUT) { setStatus("问题最多 1500 字，请精简后发送。", "error"); input.focus(); return; }
    const requestText = mode === "artifact" ? artifactRequest(text) : text;
    if ([...requestText].length > MAX_INPUT) { setStatus("请稍微精简补充需求，再生成工程书。", "error"); return; }
    controller = new AbortController();
    setBusy(true);
    let assistant;
    let sent = false;
    try {
      await ensureSession(controller.signal);
      if (!window.crypto?.randomUUID) throw new Error("请使用 HTTPS 页面打开 AI 问答。");
      const visibleText = mode === "artifact" ? (text ? text + "\n生成 I-Lang 工程书。" : "根据本次对话生成 I-Lang 工程书。") : text;
      appendMessage("user", visibleText);
      hasConversation = true;
      assistant = appendMessage("assistant", mode === "artifact" ? "正在整理本次对话中的需求与资料…" : "");
      if (input.value.trim() === text) input.value = "";
      updateCount();
      setStatus(mode === "artifact" ? "正在生成工程书…" : "正在查阅资料并回答…");
      scrollBottom(true);
      sent = true;
      const response = await fetch("/api/chat/message", {
        method: "POST", credentials: "same-origin", cache: "no-store", signal: controller.signal,
        headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
        body: JSON.stringify({ message: requestText, requestId: crypto.randomUUID(), mode,
          context: text, reuseLastAnswer: mode === "artifact" && !text })
      });
      if (!response.ok) {
        let payload;
        try { payload = await response.json(); } catch (_) { payload = {}; }
        if ([401, 403].includes(response.status)) sessionReady = false;
        throw new Error(typeof payload.message === "string" ? payload.message : "AI 暂时无法回答，请稍后重试。");
      }
      await readAnswer(response, assistant, mode);
      setStatus(mode === "artifact" ? "工程书已就绪。也可以继续补充需求。" : "可以在上方输入框继续追问。");
      input.placeholder = "继续追问，或补充你的系统、型号与具体问题…";
    } catch (error) {
      const stopped = error.name === "AbortError";
      const message = stopped ? "已停止接收。可以继续追问或重新生成。" : String(error.message || "暂时无法完成，请重试。");
      setStatus(message, stopped ? "normal" : "error");
      if (assistant) {
        if (mode === "artifact" && !assistant.artifact) assistant.body.textContent = "工程书尚未生成。";
        assistant.article.append(node("p", "chat-message-note", message));
      }
      // Keep the failed question available without silently resending it.
      if (sent && !stopped && !input.value) input.value = text;
      updateCount();
    } finally {
      controller = null;
      setBusy(false);
    }
  }

  async function startNew() {
    if (busy) return;
    setBusy(true);
    stop.hidden = true;
    const resetController = new AbortController();
    const timeout = setTimeout(() => resetController.abort(), 30000);
    try {
      if (sessionReady || hasConversation) await postJSON("/api/chat/reset", {}, resetController.signal);
      transcript.replaceChildren();
      sessionReady = false;
      hasConversation = false;
      input.value = "";
      input.placeholder = "例如：我的 AX58U V2 应该查哪个梅林版本？";
      updateCount();
      setStatus("已清空对话，可以开始一个新问题。");
      input.focus();
    } catch (error) { setStatus(error.name === "AbortError" ? "清空请求超时，请重试。" : String(error.message || "暂时无法清空，请重试。"), "error"); }
    finally { clearTimeout(timeout); setBusy(false); }
  }

  function updateCount() { counter.textContent = [...input.value].length + " / " + MAX_INPUT; }
  ask.hidden = false;
  ask.addEventListener("click", () => send("answer"));
  artifactButton.addEventListener("click", () => send("artifact"));
  stop.addEventListener("click", () => controller?.abort());
  reset.addEventListener("click", startNew);
  input.addEventListener("input", updateCount);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      send("answer");
    }
  });
  document.getElementById("chat-input-help").textContent = "Enter 提问，Shift + Enter 换行；也可以搜索工具目录。";
  updateCount();
})();
