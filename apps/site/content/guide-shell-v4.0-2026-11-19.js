/* Original progressive shell. Document navigation and GET search work without JS. */
(() => {
  "use strict";
  const root = document.documentElement;
  const choiceKey = "fanqiang.guide:theme:v4";
  const choices = ["system", "light", "dark"];
  const labels = { system: "跟随系统", light: "浅色模式", dark: "深色模式" };
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  let choice = "system";
  try {
    const stored = window.localStorage.getItem(choiceKey);
    if (choices.includes(stored)) choice = stored;
  } catch (_) { /* A blocked preference store does not prevent theme switching. */ }
  // This script runs in the head before the v4 stylesheet. Resolve the first
  // paint here; DOM initialization below must not animate a second theme change.
  root.dataset.theme = choice === "system" ? (media?.matches ? "dark" : "light") : choice;
  root.dataset.fgThemeChoice = choice;

  const initializeShell = () => {
  const themeButtons = [...document.querySelectorAll("[data-fg-theme-toggle]")];
  const renderThemeControls = () => {
    themeButtons.forEach(button => {
      button.hidden = false;
      const label = button.querySelector("[data-fg-theme-label]");
      if (label) label.textContent = labels[choice];
      const next = choices[(choices.indexOf(choice) + 1) % choices.length];
      button.setAttribute("aria-label", `${labels[choice]}，切换为${labels[next]}`);
      button.title = `${labels[choice]}，切换为${labels[next]}`;
    });
  };
  const renderTheme = () => {
    root.dataset.theme = choice === "system" ? (media?.matches ? "dark" : "light") : choice;
    root.dataset.fgThemeChoice = choice;
    renderThemeControls();
  };
  renderThemeControls();
  themeButtons.forEach(button => button.addEventListener("click", () => {
    choice = choices[(choices.indexOf(choice) + 1) % choices.length];
    try { window.localStorage.setItem(choiceKey, choice); } catch (_) { /* Session-only choice. */ }
    renderTheme();
  }));
  const followSystem = () => { if (choice === "system") renderTheme(); };
  if (media?.addEventListener) media.addEventListener("change", followSystem);
  else if (media?.addListener) media.addListener(followSystem);
  window.addEventListener("storage", event => {
    if (event.key !== choiceKey) return;
    choice = choices.includes(event.newValue) ? event.newValue : "system";
    renderTheme();
  });

  const dialog = document.getElementById("fg-search-dialog");
  const launchers = [...document.querySelectorAll("[data-fg-search-open]")];
  const input = document.getElementById("fg-search-input");
  let returnFocus = null;
  const openSearch = opener => {
    if (!dialog || typeof dialog.showModal !== "function") return false;
    if (!dialog.open) {
      returnFocus = opener instanceof HTMLElement ? opener : document.activeElement;
      try { dialog.showModal(); } catch (_) { return false; }
    }
    input?.focus();
    input?.select();
    return true;
  };
  const closeSearch = () => { if (dialog?.open) dialog.close(); };
  launchers.forEach(link => {
    const key = link.querySelector("kbd");
    if (key && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)) key.textContent = "⌘ K";
    link.addEventListener("click", event => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      if (openSearch(link)) event.preventDefault();
    });
  });
  document.addEventListener("keydown", event => {
    if (event.key.toLowerCase() !== "k" || !(event.ctrlKey || event.metaKey) || event.altKey || event.repeat) return;
    if (openSearch(document.activeElement)) event.preventDefault();
  });
  if (dialog) {
    dialog.querySelector("[data-fg-search-close]")?.addEventListener("click", closeSearch);
    dialog.addEventListener("cancel", event => { event.preventDefault(); closeSearch(); });
    dialog.addEventListener("close", () => {
      if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
      returnFocus = null;
    });
    dialog.addEventListener("click", event => {
      if (event.target !== dialog) return;
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) closeSearch();
    });
    dialog.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeSearch();
        return;
      }
      if (event.key !== "Tab") return;
      const items = [...dialog.querySelectorAll("a[href],button:not([disabled]),input:not([disabled]),[tabindex='0']")]
        .filter(item => !item.hidden && item.getClientRects().length);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    });
  }

  // Mark an existing heading link without changing anchors or scroll behavior.
  const tocLinks = [...document.querySelectorAll(".fg-toc a[href^='#']")];
  if ("IntersectionObserver" in window && tocLinks.length) {
    const targets = new Map();
    tocLinks.forEach(link => {
      try {
        const target = document.getElementById(decodeURIComponent(link.hash.slice(1)));
        if (target) targets.set(target, link);
      } catch (_) { /* Preserve an unusual source anchor as a normal link. */ }
    });
    const observer = new IntersectionObserver(entries => {
      const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (!visible.length) return;
      tocLinks.forEach(link => link.removeAttribute("aria-current"));
      targets.get(visible[0].target)?.setAttribute("aria-current", "location");
    }, { rootMargin: "-12% 0px -65% 0px", threshold: 0 });
    targets.forEach((_, target) => observer.observe(target));
  }
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeShell, { once: true });
  } else {
    initializeShell();
  }
})();
