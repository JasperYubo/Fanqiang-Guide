/* Adapted from ilang.ai's inline WeChat/QQ guard (2026-09-13).
   Source: https://github.com/ilang-ai/ilang.ai/blob/main/index.html
   Keep the external-browser notice, hidden content and top-right menu cue.
   A standalone MQQBrowser token is intentionally not treated as the QQ app. */
(function () {
  "use strict";
  var ua = String(navigator.userAgent || "").toLowerCase();
  var restricted = ua.indexOf("micromessenger") !== -1 || /(?:^|[\s;(])(?:qq|tim)\/\d/.test(ua);
  if (!restricted) return;
  window.__FG_EXTERNAL_BROWSER_REQUIRED__ = true;
  document.documentElement.classList.add("fg-external-browser");

  function element(tag, className, text) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }
  var mounted = false;
  function mount() {
    if (mounted || !document.body) return;
    mounted = true;
    var notice = element("section", "fg-external-browser-notice");
    notice.id = "fg-external-browser-guard";
    notice.setAttribute("role", "dialog");
    notice.setAttribute("aria-modal", "true");
    notice.setAttribute("aria-labelledby", "fg-external-browser-title");
    var arrow = element("span", "fg-external-browser-arrow", "↗");
    arrow.setAttribute("aria-hidden", "true");
    notice.appendChild(arrow);
    var inner = element("div", "fg-external-browser-inner");
    var title = element("h1", "", "请在浏览器中打开");
    title.id = "fg-external-browser-title";
    inner.appendChild(title);
    inner.appendChild(element("p", "fg-external-browser-instruction", "点击右上角…，选择在浏览器打开"));
    var copy = element("button", "fg-external-browser-copy", "复制网址");
    copy.type = "button";
    inner.appendChild(copy);
    var status = element("p", "fg-external-browser-status", "也可以复制网址，到手机浏览器粘贴打开。");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    inner.appendChild(status);
    var fallback = element("div", "fg-external-browser-fallback");
    fallback.hidden = true;
    var label = element("label", "", "长按下方网址，选择复制，再到浏览器粘贴打开。");
    label.htmlFor = "fg-external-browser-url";
    var url = element("textarea", "");
    url.id = "fg-external-browser-url";
    url.value = window.location.href;
    url.readOnly = true;
    url.rows = 3;
    url.setAttribute("aria-label", "当前页面网址，可长按复制");
    fallback.appendChild(label);
    fallback.appendChild(url);
    inner.appendChild(fallback);
    notice.appendChild(inner);

    copy.addEventListener("click", async function () {
      copy.disabled = true;
      copy.textContent = "正在复制…";
      try {
        if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") throw new Error();
        await navigator.clipboard.writeText(window.location.href);
        copy.textContent = "已复制网址";
        status.textContent = "网址已复制，请到手机浏览器粘贴打开。";
      } catch (_) {
        copy.textContent = "复制网址";
        status.textContent = "复制未成功，请长按下方网址并复制。";
        fallback.hidden = false;
        url.focus();
        url.select();
      } finally { copy.disabled = false; }
    });

    function hidePageElements() {
      for (var child of document.body.children) {
        if (child !== notice) {
          child.inert = true;
          child.setAttribute("aria-hidden", "true");
        }
      }
    }
    hidePageElements();
    document.body.appendChild(notice);
    new MutationObserver(hidePageElements).observe(document.body, { childList: true });
  }
  // The head flag and stylesheet hide content before body parsing/interaction.
  var observer = new MutationObserver(function () {
    mount();
    if (mounted) observer.disconnect();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  mount();
})();
