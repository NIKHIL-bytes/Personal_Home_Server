(() => {
  let currentPath = '';
  let isListView = false;

  const grid = document.getElementById('fileGrid');
  const emptyState = document.getElementById('fileEmptyState');
  const breadcrumbs = document.getElementById('breadcrumbs');

  document.addEventListener('DOMContentLoaded', () => {
    load();

    document.getElementById('uploadInput').addEventListener('change', (e) => uploadFiles(e.target.files));
    document.getElementById('newFolderBtn').addEventListener('click', createFolder);
    document.getElementById('viewToggleBtn').addEventListener('click', toggleView);

    document.addEventListener('click', (e) => {
      document.querySelectorAll('.file-actions-menu').forEach(m => {
        if (!m.contains(e.target) && !m.dataset.justOpened) m.remove();
      });
    });
  });

  async function load() {
    try {
      const data = await api(`/api/files?path=${encodeURIComponent(currentPath)}`);
      renderBreadcrumbs();
      renderItems(data.items);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  function renderBreadcrumbs() {
    const parts = currentPath ? currentPath.split('/') : [];
    let html = `<a href="#" data-path="">Home</a>`;
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

  function renderItems(items) {
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
          openViewer(item, 'files');
        }
      });
      card.querySelector('.file-menu-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        openMenu(card, JSON.parse(card.dataset.item));
      });
    });
  }

  function itemHtml(item) {
    const icon = item.is_dir ? '📁' : (FILE_ICONS[item.type] || '📄');
    const meta = item.is_dir ? 'Folder' : item.size_display;
    return `
      <div class="file-card" data-item='${JSON.stringify(item).replace(/'/g, "&#39;")}'>
        <button class="file-menu-btn" aria-label="Actions">⋮</button>
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
    window.location.href = `/api/files/download?path=${encodeURIComponent(path)}`;
  }

  async function renameItem(item) {
    const newName = prompt('Rename to:', item.name);
    if (!newName || newName === item.name) return;
    try {
      await api(`/api/files/rename?path=${encodeURIComponent(item.path)}&new_name=${encodeURIComponent(newName)}`, { method: 'PATCH' });
      showToast('Renamed', 'success');
      load();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function deleteItem(item) {
    if (!confirm(`Delete "${item.name}"? This action cannot be undone.`)) return;
    try {
      await api(`/api/files?path=${encodeURIComponent(item.path)}`, { method: 'DELETE' });
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
      await api(`/api/files/folder?path=${encodeURIComponent(currentPath)}&name=${encodeURIComponent(name)}`, { method: 'POST' });
      showToast('Folder created', 'success');
      load();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  function uploadFiles(fileList) {
    const files = Array.from(fileList);
    if (!files.length) return;
    const wrap = document.getElementById('uploadProgressWrap');
    const fill = document.getElementById('uploadProgressFill');
    const label = document.getElementById('uploadProgressLabel');
    wrap.hidden = false;

    let index = 0;
    function next() {
      if (index >= files.length) {
        wrap.hidden = true;
        load();
        showToast('Upload complete', 'success');
        return;
      }
      const file = files[index];
      label.textContent = `Uploading ${file.name} (${index + 1}/${files.length})`;
      const formData = new FormData();
      formData.append('file', file);

      const xhr = new XMLHttpRequest();
      xhr.open('POST', `/api/files/upload?path=${encodeURIComponent(currentPath)}`);

      const csrf = document.cookie.split('; ').find(row => row.startsWith('hs_csrf='));
      if (csrf) {
        xhr.setRequestHeader(
          'X-CSRF-Token',
          decodeURIComponent(csrf.split('=')[1])
        );
      }
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) fill.style.width = `${Math.round((e.loaded / e.total) * 100)}%`;
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          index++;
          next();
        } else {
          wrap.hidden = true;
          let msg = 'Upload failed';
          try { msg = JSON.parse(xhr.responseText).detail || msg; } catch (e) {}
          showToast(msg, 'error');
        }
      };
      xhr.onerror = () => { wrap.hidden = true; showToast('Upload failed', 'error'); };
      xhr.send(formData);
    }
    next();
  }

  function toggleView() {
    isListView = !isListView;
    grid.classList.toggle('list-view', isListView);
    document.getElementById('viewToggleBtn').textContent = isListView ? 'List' : 'Grid';
  }
})();
