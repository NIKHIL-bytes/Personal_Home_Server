(() => {
  let usersCache = [];
  let userDetailId = null;
  let userFilesPath = '';
  let logFilters = { user: '', action: '' };

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.admin-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        document.querySelectorAll('.admin-section').forEach(s => s.hidden = true);
        const section = document.getElementById(`admin${capitalize(tab.dataset.tab)}`);
        section.hidden = false;
        if (tab.dataset.tab === 'users') loadUsers();
        if (tab.dataset.tab === 'logs') loadLogs();
      });
    });

    document.getElementById('createUserBtn').addEventListener('click', () => {
      document.getElementById('createUserModal').hidden = false;
    });
    document.getElementById('cancelCreateUser').addEventListener('click', () => {
      document.getElementById('createUserModal').hidden = true;
    });
    document.getElementById('createUserForm').addEventListener('submit', createUser);

    document.getElementById('userSearchInput').addEventListener('input', debounce((e) => {
      renderUsers(filterUsers(e.target.value));
    }, 150));

    document.getElementById('userDetailBackBtn').addEventListener('click', closeUserDetail);
    document.getElementById('userDetailForceLogoutBtn').addEventListener('click', () => forceLogout(userDetailId));
    document.getElementById('userDetailResetPwBtn').addEventListener('click', () => resetPassword(userDetailId));
    document.getElementById('userDetailDeleteDataBtn').addEventListener('click', () => deleteUserData(userDetailId));
    document.getElementById('userFilesNewFolderBtn').addEventListener('click', createUserFolder);

    document.getElementById('logFilterBtn').addEventListener('click', () => {
      logFilters.user = document.getElementById('logUserFilter').value.trim();
      logFilters.action = document.getElementById('logActionFilter').value.trim();
      loadLogs();
    });
    document.getElementById('logFilterClearBtn').addEventListener('click', () => {
      document.getElementById('logUserFilter').value = '';
      document.getElementById('logActionFilter').value = '';
      logFilters = { user: '', action: '' };
      loadLogs();
    });

    document.addEventListener('click', (e) => {
      document.querySelectorAll('.file-actions-menu').forEach(m => {
        if (!m.contains(e.target) && !m.dataset.justOpened) m.remove();
      });
    });

    loadStats();
    setInterval(loadStats, 8000); // gentle polling interval, easy on 4GB RAM hardware
  });

  function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  // ---------- Overview ----------

  async function loadStats() {
    try {
      const data = await api('/api/admin/stats');
      setBar('cpuFill', 'cpuValue', data.cpu_percent);
      setBar('ramFill', 'ramValue', data.ram_percent);
      setBar('diskFill', 'diskValue', data.disk_percent, `${data.disk_used_display} / ${data.disk_total_display}`);
      document.getElementById('statUserCount').textContent = data.user_count;
      document.getElementById('statSessions').textContent = data.active_sessions;
      document.getElementById('statUptime').textContent = formatUptime(data.uptime_seconds);
    } catch (err) { /* silent on background poll */ }
  }

  function setBar(fillId, valueId, percent, overrideLabel) {
    const fill = document.getElementById(fillId);
    const value = document.getElementById(valueId);
    if (percent == null) {
      value.textContent = 'Unavailable (install psutil)';
      fill.style.width = '0%';
      return;
    }
    fill.style.width = `${percent}%`;
    value.textContent = overrideLabel || `${percent}%`;
  }

  function formatUptime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  }

  // ---------- Users ----------

  async function loadUsers() {
    const tbody = document.getElementById('usersTableBody');
    try {
      usersCache = await api('/api/admin/users');
      renderUsers(usersCache);
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="5">${escapeHtml(err.message)}</td></tr>`;
    }
  }

  function filterUsers(query) {
    const q = query.trim().toLowerCase();
    if (!q) return usersCache;
    return usersCache.filter(u =>
      u.username.toLowerCase().includes(q) || u.display_name.toLowerCase().includes(q));
  }

  function renderUsers(users) {
    const tbody = document.getElementById('usersTableBody');
    if (!users.length) {
      tbody.innerHTML = `<tr><td colspan="5">No users match.</td></tr>`;
      return;
    }
    tbody.innerHTML = users.map(u => `
      <tr>
        <td>${escapeHtml(u.display_name)}<br><span class="file-meta">@${escapeHtml(u.username)}</span></td>
        <td><span class="badge ${u.role === 'admin' ? 'admin-role' : 'user-role'}">${u.role}</span></td>
        <td><span class="badge ${u.is_active ? 'active' : 'inactive'}">${u.is_active ? 'Active' : 'Disabled'}</span></td>
        <td>${humanFromBytes(u.storage_quota)}</td>
        <td class="table-actions">
          <button class="btn btn-secondary" data-action="browse" data-id="${u.id}">Browse</button>
          <button class="btn btn-secondary" data-action="toggle" data-id="${u.id}" data-active="${u.is_active}">${u.is_active ? 'Disable' : 'Enable'}</button>
          <button class="btn btn-secondary" data-action="reset" data-id="${u.id}">Reset PW</button>
          <button class="btn btn-danger" data-action="delete" data-id="${u.id}" data-name="${escapeHtml(u.username)}">Delete</button>
        </td>
      </tr>`).join('');

    tbody.querySelectorAll('button').forEach(btn => btn.addEventListener('click', handleUserAction));
  }

  function humanFromBytes(n) {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = n, i = 0;
    while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
    return `${size.toFixed(1)} ${units[i]}`;
  }

  async function handleUserAction(e) {
    const btn = e.currentTarget;
    const id = btn.dataset.id;
    const action = btn.dataset.action;

    if (action === 'browse') {
      openUserDetail(id);
    }

    if (action === 'toggle') {
      const nowActive = btn.dataset.active === 'true';
      try {
        await api(`/api/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !nowActive }) });
        showToast(nowActive ? 'User disabled' : 'User enabled', 'success');
        loadUsers();
      } catch (err) { showToast(err.message, 'error'); }
    }

    if (action === 'reset') {
      await resetPassword(id);
    }

    if (action === 'delete') {
      const alsoWipe = confirm(
        `Delete user "${btn.dataset.name}"? This cannot be undone.\n\n` +
        `Press OK to delete the ACCOUNT ONLY (their files stay on disk), ` +
        `or press Cancel to choose whether to also wipe their storage.`
      );
      let deleteData = false;
      if (!alsoWipe) {
        deleteData = confirm(
          `Also permanently delete "${btn.dataset.name}"'s storage (all their files)?\n\n` +
          `Press OK to delete the account AND all files. Press Cancel to abort entirely.`
        );
        if (!deleteData) return; // user aborted the whole operation
      }
      try {
        await api(`/api/admin/users/${id}?delete_data=${deleteData}`, { method: 'DELETE' });
        showToast('User deleted', 'success');
        loadUsers();
      } catch (err) { showToast(err.message, 'error'); }
    }
  }

  async function resetPassword(id) {
    const pw = prompt('New password (min 8 characters):');
    if (!pw) return;
    try {
      await api(`/api/admin/users/${id}/reset-password`, { method: 'POST', body: JSON.stringify({ new_password: pw }) });
      showToast('Password reset — user has been logged out everywhere', 'success');
    } catch (err) { showToast(err.message, 'error'); }
  }

  async function forceLogout(id) {
    if (!id) return;
    if (!confirm('Force logout this user from all devices?')) return;
    try {
      await api(`/api/admin/users/${id}/force-logout`, { method: 'POST' });
      showToast('User logged out everywhere', 'success');
    } catch (err) { showToast(err.message, 'error'); }
  }

  async function deleteUserData(id) {
    if (!id) return;
    if (!confirm('Permanently delete ALL files for this user? The account itself will be kept. This cannot be undone.')) return;
    try {
      await api(`/api/admin/users/${id}/delete-data`, { method: 'POST', body: JSON.stringify({ confirm: true }) });
      showToast('User storage wiped', 'success');
      userFilesPath = '';
      loadUserFiles();
      loadUserDetailStats(id);
    } catch (err) { showToast(err.message, 'error'); }
  }

  async function createUser(e) {
    e.preventDefault();
    const form = new FormData(e.target);
    try {
      await api('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify({
          username: form.get('username'),
          display_name: form.get('display_name'),
          password: form.get('password'),
          role: form.get('role'),
        }),
      });
      showToast('User created', 'success');
      document.getElementById('createUserModal').hidden = true;
      e.target.reset();
      loadUsers();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  // ---------- User detail + storage browser ----------

  function openUserDetail(id) {
    userDetailId = id;
    userFilesPath = '';
    document.querySelectorAll('.admin-section').forEach(s => s.hidden = true);
    document.getElementById('adminUserDetail').hidden = false;
    loadUserDetailStats(id);
    loadUserFiles();
  }

  function closeUserDetail() {
    userDetailId = null;
    document.querySelectorAll('.admin-section').forEach(s => s.hidden = true);
    document.getElementById('adminUsers').hidden = false;
    loadUsers();
  }

  async function loadUserDetailStats(id) {
    try {
      const u = await api(`/api/admin/users/${id}`);
      document.getElementById('userDetailName').textContent = u.display_name;
      document.getElementById('userDetailMeta').textContent =
        `@${u.username} · ${u.role === 'admin' ? 'Administrator' : 'User'} · ${u.is_active ? 'Active' : 'Disabled'}`;
      document.getElementById('userDetailStorage').textContent = u.storage_used_display;
      document.getElementById('userDetailFileCount').textContent = u.file_count;
      document.getElementById('userDetailQuota').textContent = u.storage_quota_display;
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function loadUserFiles() {
    const grid = document.getElementById('userFilesGrid');
    const emptyState = document.getElementById('userFilesEmptyState');
    try {
      const data = await api(`/api/admin/users/${userDetailId}/files?path=${encodeURIComponent(userFilesPath)}`);
      renderUserFilesBreadcrumbs();
      if (!data.items.length) {
        grid.innerHTML = '';
        emptyState.hidden = false;
        return;
      }
      emptyState.hidden = true;
      grid.innerHTML = data.items.map(userFileItemHtml).join('');

      grid.querySelectorAll('.file-card').forEach(card => {
        card.addEventListener('click', (e) => {
          if (e.target.closest('.file-menu-btn') || e.target.closest('.file-actions-menu')) return;
          const item = JSON.parse(card.dataset.item);
          if (item.is_dir) {
            userFilesPath = item.path;
            loadUserFiles();
          } else {
            openViewer(item, 'admin', userDetailId);
          }
        });
        card.querySelector('.file-menu-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          openUserFileMenu(card, JSON.parse(card.dataset.item));
        });
      });
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  function renderUserFilesBreadcrumbs() {
    const breadcrumbs = document.getElementById('userFilesBreadcrumbs');
    const parts = userFilesPath ? userFilesPath.split('/') : [];
    let html = `<a href="#" data-path="">Root</a>`;
    let acc = '';
    parts.forEach(p => {
      acc = acc ? `${acc}/${p}` : p;
      html += ` <span>/</span> <a href="#" data-path="${escapeHtml(acc)}">${escapeHtml(p)}</a>`;
    });
    breadcrumbs.innerHTML = html;
    breadcrumbs.querySelectorAll('a').forEach(a => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        userFilesPath = a.dataset.path;
        loadUserFiles();
      });
    });
  }

  function userFileItemHtml(item) {
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

  function openUserFileMenu(card, item) {
    document.querySelectorAll('.file-actions-menu').forEach(m => m.remove());
    const menu = document.createElement('div');
    menu.className = 'file-actions-menu';
    menu.dataset.justOpened = '1';
    const actions = [];
    if (!item.is_dir) actions.push(['Download', () => {
      window.location.href = `/api/admin/users/${userDetailId}/files/download?path=${encodeURIComponent(item.path)}`;
    }]);
    actions.push(['Rename', () => renameUserFile(item)]);
    actions.push(['Delete', () => deleteUserFile(item), true]);
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

  async function renameUserFile(item) {
    const newName = prompt('Rename to:', item.name);
    if (!newName || newName === item.name) return;
    try {
      await api(`/api/admin/users/${userDetailId}/files/rename?path=${encodeURIComponent(item.path)}&new_name=${encodeURIComponent(newName)}`, { method: 'PATCH' });
      showToast('Renamed', 'success');
      loadUserFiles();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function deleteUserFile(item) {
    if (!confirm(`Delete "${item.name}"? This action cannot be undone.`)) return;
    try {
      await api(`/api/admin/users/${userDetailId}/files?path=${encodeURIComponent(item.path)}`, { method: 'DELETE' });
      showToast('Deleted', 'success');
      loadUserFiles();
      loadUserDetailStats(userDetailId);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function createUserFolder() {
    const name = prompt('Folder name:');
    if (!name) return;
    try {
      await api(`/api/admin/users/${userDetailId}/files/folder?path=${encodeURIComponent(userFilesPath)}&name=${encodeURIComponent(name)}`, { method: 'POST' });
      showToast('Folder created', 'success');
      loadUserFiles();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  // ---------- Audit logs ----------

  async function loadLogs() {
    const tbody = document.getElementById('logsTableBody');
    try {
      const users = usersCache.length ? usersCache : await api('/api/admin/users');
      if (!usersCache.length) usersCache = users;
      const params = new URLSearchParams({ page_size: '100' });
      if (logFilters.action) params.set('action', logFilters.action);
      if (logFilters.user) {
        const match = users.find(u => u.username.toLowerCase() === logFilters.user.toLowerCase());
        if (match) params.set('user_id', match.id);
      }
      const data = await api(`/api/admin/logs?${params.toString()}`);
      tbody.innerHTML = data.items.map(l => `
        <tr>
          <td>${escapeHtml(l.timestamp)}</td>
          <td>${escapeHtml(l.username || '—')}</td>
          <td>${escapeHtml(l.action)}</td>
          <td>${escapeHtml(l.target_id || '—')}</td>
          <td>${escapeHtml(l.ip_address || '—')}</td>
        </tr>`).join('');
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="5">${escapeHtml(err.message)}</td></tr>`;
    }
  }
})();
