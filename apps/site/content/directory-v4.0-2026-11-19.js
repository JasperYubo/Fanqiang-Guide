"use strict";
(() => {
  const normalize = value => String(value || "").normalize("NFKC").toLocaleLowerCase().trim();
  const collator = new Intl.Collator("zh-CN", {numeric: true, sensitivity: "base"});
  for (const browser of document.querySelectorAll("[data-fg-directory]")) {
    const extra = browser.querySelector("[data-fg-directory-extra]");
    const query = browser.querySelector("[data-query]");
    const filters = Array.from(browser.querySelectorAll("[data-filter]"));
    const addedFilters = Array.from(browser.querySelectorAll("[data-fg-directory-filter]"));
    const sort = browser.querySelector("[data-fg-directory-sort]");
    const count = browser.querySelector("[data-count]");
    const empty = browser.querySelector("[data-empty]");
    const groups = Array.from(browser.querySelectorAll("[data-group]"));
    const records = Array.from(browser.querySelectorAll("[data-record]"));
    if (!extra || !query || !sort || !count || !empty) continue;
    const indexed = records.map(node => ({
      node,
      text: normalize(node.dataset.search),
      platforms: JSON.parse(node.dataset.fgPlatforms || "[]"),
      name: node.dataset.fgName || "",
      checked: node.dataset.fgChecked || "",
      order: Number(node.dataset.fgOrder),
      parent: node.parentElement,
    }));
    const containers = Array.from(new Set(indexed.map(record => record.parent)));
    const params = new URLSearchParams(window.location.search);
    for (const control of [...addedFilters, sort]) {
      const key = control === sort ? "sort" : control.dataset.fgDirectoryFilter;
      const value = params.get(key);
      if (value !== null && Array.from(control.options).some(option => option.value === value)) control.value = value;
    }
    let appliedSort = "";
    function apply() {
      const words = normalize(query.value).split(/\s+/).filter(Boolean);
      let shown = 0;
      for (const record of indexed) {
        const matches = words.every(word => record.text.includes(word)) &&
          filters.every(filter => !filter.value || record.node.dataset[filter.dataset.filter] === filter.value) &&
          addedFilters.every(filter => !filter.value || (filter.dataset.fgDirectoryFilter === "platform"
            ? record.platforms.includes(filter.value)
            : record.node.dataset.fgMaintenance === filter.value));
        record.node.hidden = !matches;
        if (matches) shown++;
      }
      if (sort.value !== appliedSort) {
        const compare = (a, b) => {
          if (sort.value === "name-asc") return collator.compare(a.name, b.name) || a.order - b.order;
          if (sort.value === "name-desc") return collator.compare(b.name, a.name) || a.order - b.order;
          if (sort.value === "checked-desc") return b.checked.localeCompare(a.checked) || a.order - b.order;
          return a.order - b.order;
        };
        for (const container of containers) {
          const children = indexed.filter(record => record.parent === container).sort(compare);
          for (const record of children) container.appendChild(record.node);
        }
        appliedSort = sort.value;
      }
      for (const group of groups) {
        group.hidden = !Array.from(group.querySelectorAll("[data-record]")).some(node => !node.hidden);
      }
      count.textContent = `显示 ${shown} / ${records.length} ${browser.dataset.unit}`;
      empty.hidden = shown !== 0;
    }
    // The original catalog listeners run synchronously. Reapply the combined
    // predicate once at the end of the event so they cannot erase extra filters.
    let pending = false;
    function schedule() {
      if (pending) return;
      pending = true;
      queueMicrotask(() => { pending = false; apply(); });
    }
    browser.addEventListener("input", event => {
      if (event.target === query) schedule();
    });
    browser.addEventListener("change", event => {
      if (filters.includes(event.target) || addedFilters.includes(event.target) || event.target === sort) schedule();
    });
    browser.addEventListener("click", event => {
      if (!event.target.closest("[data-clear], .catalog-category-nav a")) return;
      for (const filter of addedFilters) filter.value = "";
      sort.value = "";
      schedule();
    });
    apply();
    extra.hidden = false;
  }
})();
