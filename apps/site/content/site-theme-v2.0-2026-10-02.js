/* The native details menu works without JavaScript. This only adds close behavior. */
(() => {
  const menus = [...document.querySelectorAll('.mobile-nav')];
  if (!menus.length) return;
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    for (const menu of menus) {
      if (!menu.open) continue;
      menu.open = false;
      menu.querySelector('summary')?.focus();
    }
  });
  document.addEventListener('pointerdown', event => {
    for (const menu of menus) if (menu.open && !menu.contains(event.target)) menu.open = false;
  });
  for (const menu of menus) {
    for (const link of menu.querySelectorAll('nav a')) link.addEventListener('click', () => { menu.open = false; });
  }
})();
