/* Copy only pre.textContent. Native details keep all content available without JS. */
(() => {
  "use strict";
  const roots = Array.from(document.querySelectorAll("[data-reading-code]"));
  const selectAll = (field) => {
    field.focus({ preventScroll: true });
    field.select();
    field.setSelectionRange(0, field.value.length);
  };

  const fallbackCopy = (text, root, status, button) => {
    const field = document.createElement("textarea");
    field.value = text;
    field.readOnly = true;
    field.className = "reading-code-manual";
    field.setAttribute("aria-label", "完整代码，请手动复制");
    field.setAttribute("spellcheck", "false");
    field.setAttribute("wrap", "off");
    // Keep the temporary field renderable for older clipboard implementations.
    field.style.cssText = "position:fixed;left:0;top:0;width:1px;height:1px;min-height:0;margin:0;padding:0;opacity:0;pointer-events:none";
    root.appendChild(field);
    let copied = false;
    try {
      selectAll(field);
      copied = typeof document.execCommand === "function" && document.execCommand("copy") === true;
    } catch (_) {
      copied = false;
    }
    if (copied) {
      field.remove();
      return true;
    }
    // Never claim success if both clipboard APIs failed. Leave selectable text.
    field.removeAttribute("style");
    status.textContent = "未能自动复制。完整代码已选中，请按 Ctrl+C / ⌘C，或长按复制。";
    try { selectAll(field); } catch (_) { /* The visible field remains manually selectable. */ }
    field.scrollIntoView({ block: "nearest", inline: "nearest" });
    return false;
  };

  roots.forEach((root) => {
    if (root.dataset.readingReady === "true") return;
    const button = root.querySelector("[data-copy-code]");
    const pre = root.querySelector("pre");
    const status = root.querySelector(".reading-code-status");
    if (!button || !pre || !status) return;
    if (!pre.hasAttribute("tabindex")) pre.tabIndex = 0;
    const buttonText = button.querySelector("span");
    let resetTimer;
    button.addEventListener("click", async () => {
      window.clearTimeout(resetTimer);
      if (buttonText) buttonText.textContent = "复制代码";
      if (button.disabled) return;
      button.disabled = true;
      root.querySelectorAll(".reading-code-manual").forEach((field) => field.remove());
      status.textContent = "正在复制…";
      const text = pre.textContent;
      let copied = false;
      try {
        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
          await navigator.clipboard.writeText(text);
          copied = true;
        }
      } catch (_) {
        copied = false;
      }
      try {
        if (!copied) copied = fallbackCopy(text, root, status, button);
        if (copied) {
          status.textContent = "已复制代码";
          if (buttonText) buttonText.textContent = "已复制";
          resetTimer = window.setTimeout(() => {
            if (buttonText) buttonText.textContent = "复制代码";
          }, 2500);
        }
      } catch (_) {
        status.textContent = "未能自动复制，请展开并选中代码后手动复制。";
      } finally {
        button.disabled = false;
        if (copied) button.focus({ preventScroll: true });
      }
    });
    root.dataset.readingReady = "true";
    button.hidden = false;
  });

  const openHashTarget = () => {
    if (!location.hash) return;
    let id;
    try {
      id = decodeURIComponent(location.hash.slice(1));
    } catch (_) {
      return;
    }
    const target = document.getElementById(id);
    if (!target) return;
    let changed = false;
    for (let parent = target; parent; parent = parent.parentElement) {
      if (parent.tagName === "DETAILS" && !parent.open) {
        parent.open = true;
        changed = true;
      }
    }
    if (changed) requestAnimationFrame(() => target.scrollIntoView({ block: "start" }));
  };
  openHashTarget();
  window.addEventListener("hashchange", openHashTarget);
  document.addEventListener("click", (event) => {
    const link = event.target instanceof Element && event.target.closest("a[href]");
    if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const url = new URL(link.href, location.href);
    if (url.origin === location.origin && url.pathname === location.pathname &&
        url.search === location.search && url.hash && url.hash === location.hash) {
      requestAnimationFrame(openHashTarget);
    }
  });
  let printClosed = [];
  let printing = false;
  window.addEventListener("beforeprint", () => {
    if (printing) return;
    printing = true;
    printClosed = Array.from(document.querySelectorAll("details:not([open])")).filter(
      (details) => details.closest("[data-reading-code]") || details.querySelector("[data-reading-code]")
    );
    printClosed.forEach((details) => { details.open = true; });
  });
  window.addEventListener("afterprint", () => {
    printClosed.forEach((details) => { details.open = false; });
    printClosed = [];
    printing = false;
  });
})();
