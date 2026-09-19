"use strict";
(() => {
  const normalize = value => String(value || "").normalize("NFKC").toLocaleLowerCase().trim();
  for (const browser of document.querySelectorAll("[data-catalog]")) {
    const query = browser.querySelector("[data-query]");
    const filters = Array.from(browser.querySelectorAll("[data-filter]"));
    const records = Array.from(browser.querySelectorAll("[data-record]"));
    const groups = Array.from(browser.querySelectorAll("[data-group]"));
    const indexed = records.map(node => ({node, text: normalize(node.dataset.search)}));
    const count = browser.querySelector("[data-count]");
    const empty = browser.querySelector("[data-empty]");
    const params = new URLSearchParams(window.location.search);
    query.value = params.get("q") || "";
    for (const filter of filters) {
      const supplied = params.get(filter.dataset.filter);
      if (supplied !== null && Array.from(filter.options).some(option => option.value === supplied)) filter.value = supplied;
    }
    function apply() {
      const words = normalize(query.value).split(/\s+/).filter(Boolean);
      let shown = 0;
      for (const {node, text} of indexed) {
        const matches = words.every(word => text.includes(word)) && filters.every(filter => !filter.value || node.dataset[filter.dataset.filter] === filter.value);
        node.hidden = !matches;
        if (matches) shown++;
      }
      for (const group of groups) group.hidden = !Array.from(group.querySelectorAll("[data-record]")).some(node => !node.hidden);
      count.textContent = `显示 ${shown} / ${records.length} ${browser.dataset.unit}`;
      empty.hidden = shown !== 0;
    }
    query.addEventListener("input", apply);
    for (const filter of filters) filter.addEventListener("change", apply);
    browser.querySelector("[data-clear]").addEventListener("click", () => {
      query.value = "";
      for (const filter of filters) filter.value = "";
      apply();
      query.focus();
    });
    for (const anchor of browser.querySelectorAll(".catalog-category-nav a")) {
      anchor.addEventListener("click", () => {
        query.value = "";
        for (const filter of filters) filter.value = "";
        apply();
      });
    }
    apply();
  }
})();
