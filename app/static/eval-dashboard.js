'use strict';
(() => {
  const controls = document.getElementById('scenario-controls');
  const search = document.getElementById('scenario-search');
  const scope = document.getElementById('scope-filter');
  const category = document.getElementById('category-filter');
  const cases = Array.from(document.querySelectorAll('.scenario'));
  controls.hidden = false;
  function filter() {
    const term = search.value.trim().toLowerCase();
    let count = 0;
    for (const item of cases) {
      item.hidden = !((scope.value === 'all' || item.dataset.scope === scope.value) &&
        (category.value === 'all' || item.dataset.category === category.value) && item.dataset.search.includes(term));
      if (!item.hidden) count++;
    }
    document.getElementById('result-count').textContent = `Showing ${count} of ${cases.length} scenarios`;
    document.getElementById('no-results').hidden = count !== 0;
  }
  search.addEventListener('input', filter);
  scope.addEventListener('change', filter);
  category.addEventListener('change', filter);
  document.querySelectorAll('[data-copy]').forEach(button => {
    button.addEventListener('click', async () => {
      const original = button.textContent;
      try {
        await navigator.clipboard.writeText(document.getElementById(button.dataset.copy).textContent.trim());
        button.textContent = 'Endpoint copied';
      } catch (_) {
        button.textContent = 'Select and copy the endpoint above';
      }
      setTimeout(() => { button.textContent = original; }, 3000);
    });
  });
  function openSource() {
    const target = document.getElementById(location.hash.slice(1));
    if (target && target.matches('.source')) target.open = true;
  }
  window.addEventListener('hashchange', openSource);
  openSource();
})();
