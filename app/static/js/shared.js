(() => {
  let currentPath = '';
  let activeFilter = 'all';
  let allItems = [];
  const isAdmin = document.body.querySelector('.badge.admin-role') || document.querySelector('.user-role-badge.admin');

  const grid = document.getElementById('sharedGrid');
  const emptyState = document.getElementById('sharedEmptyState');
  const breadcrumbs = document.getElementById('sharedBreadcrumbs');

  document.addEventListener('DOMContentLoaded', () => {
    load();

    const uploadInput = document.getElementById('sharedUploadInput');
    if (uploadInput) uploadInput.addEventListener('change', (e) => uploadFiles(e.target.files));

    const newFolderBtn = document.getElementById('sharedNewFolderBtn');
    if (newFolderBtn) newFolderBtn.addEventListener('click', createFolder);

    document.getElementById('sharedFilters').addEventListener('click', (e) => {
      const chip = e.target.closest('.chip');
      if (!chip) return;
      document.querySelectorAll('#sharedFilters .chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.dataset.filter;
      renderItems();
    });

    document.addEventListener('click', (e) => {
      document.querySelectorAll('.file-actions-menu').forEach(m => {
        if (!m.contains(e.target) && !m.dataset.justOpened) m.remove();
      });
    });
  });

  async function load() {
    try {
      const data = await api(`/api/shared?path=${encodeURIComponent(currentPath)}`);
      allItems = data.items;
      renderBreadcrumbs();
      renderItems();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  function renderBreadcrumbs() {
    const parts = currentPath ? currentPath.split('/') : [];
    let html = `<a href="#" data-path="">Shared</a>`;
    let acc = '';
    parts.forEach(p => {
      acc = acc ? `${acc}/${p}` : p;
      html += ` <span>/</span> <a href="#" data-path="${escapeHtml(acc)}">${escapeHtml(p)}</a>`;
    });
    breadcrumbs.innerHTML = html;
    breadcrumbs.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        currentPath = a.dataset.path;
        load();
      });
    });
  }

  function renderItems() {
    const items = allItems.filter(i => activeFilter === 'all' || i.is_dir || i.type === activeFilter);
    if (!items.length) {
      grid.innerHTML = '';
      emptyState.hidden = false;
      return;
    }
    emptyState.hidden = true;
    grid.innerHTML = items.map(itemHtml).join('');

    grid.querySelectorAll('.file-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.file-menu-btn') || e.target.closest('.file-actions-menu')) return;
        const item = JSON.parse(card.dataset.item);
        if (item.is_dir) {
          currentPath = item.path;
          load();
        } else {
          openViewer(item, 'shared');
        }
      });
      const menuBtn = card.querySelector('.file-menu-btn');
      if (menuBtn) menuBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        openMenu(card, JSON.parse(card.dataset.item));
      });
    });
  }

  function itemHtml(item) {
    const icon = item.is_dir ? '📁' : (FILE_ICONS[item.type] || '📄');
    const meta = item.is_dir ? 'Folder' : item.size_display;
    const menuBtn = isAdmin ? `<button class="file-menu-btn" aria-label="Actions">⋮</button>` : '';
    return `
      <div class="file-card" data-item='${JSON.stringify(item).replace(/'/g, "&#39;")}'>
        ${menuBtn}
        <div class="file-icon ${item.is_dir ? 'folder' : ''}">${icon}</div>
        <div class="file-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
        <div class="file-meta">${escapeHtml(meta)}</div>
      </div>`;
  }

  function openMenu(card, item) {
    document.querySelectorAll('.file-actions-menu').forEach(m => m.remove());
    const menu = document.createElement('div');
    menu.className = 'file-actions-menu';
    menu.dataset.justOpened = '1';
    const actions = [];
    if (!item.is_dir) actions.push(['Download', () => downloadFile(item.path)]);
    actions.push(['Rename', () => renameItem(item)]);
    actions.push(['Delete', () => deleteItem(item), true]);
    menu.innerHTML = actions.map(([label, , danger]) =>
      `<button class="${danger ? 'danger' : ''}">${label}</button>`).join('');
    menu.querySelectorAll('button').forEach((btn, i) => btn.addEventListener('click', (e) => {
      e.stopPropagation();
      menu.remove();
      actions[i][1]();
    }));
    card.appendChild(menu);
    setTimeout(() => { delete menu.dataset.justOpened; }, 0);
  }

  function downloadFile(path) {
    window.location.href = `/api/shared/download?path=${encodeURIComponent(path)}`;
  }

  async function renameItem(item) {
    const newName = prompt('Rename to:', item.name);
    if (!newName || newName === item.name) return;
    try {
      await api(`/api/shared/rename?path=${encodeURIComponent(item.path)}&new_name=${encodeURIComponent(newName)}`, { method: 'PATCH' });
      showToast('Renamed', 'success');
      load();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function deleteItem(item) {
    if (!confirm(`Delete "${item.name}"? This action cannot be undone.`)) return;
    try {
      await api(`/api/shared?path=${encodeURIComponent(item.path)}`, { method: 'DELETE' });
      showToast('Deleted', 'success');
      load();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function createFolder() {
    const name = prompt('Folder name:');
    if (!name) return;
    try {
      await api(`/api/shared/folder?path=${encodeURIComponent(currentPath)}&name=${encodeURIComponent(name)}`, { method: 'POST' });
      showToast('Folder created', 'success');
      load();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  function uploadFiles(fileList) {
    const files = Array.from(fileList);
    files.forEach(async (file) => {
      const formData = new FormData();
      formData.append('file', file);
      try {
        await api(`/api/shared/upload?path=${encodeURIComponent(currentPath)}`, { method: 'POST', body: formData });
      } catch (err) {
        showToast(`${file.name}: ${err.message}`, 'error');
      }
    });
    setTimeout(load, 800);
  }
})();
