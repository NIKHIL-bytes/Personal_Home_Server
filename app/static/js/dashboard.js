document.addEventListener('DOMContentLoaded', async () => {
  loadStorage();
  loadStatus();
  loadActivity();
});

async function loadStorage() {
  try {
    const data = await api('/api/files/storage');
    const pct = data.disk_total ? Math.round(((data.disk_total - data.disk_free) / data.disk_total) * 100) : 0;
    document.getElementById('storageFill').style.width = `${pct}%`;
    document.getElementById('storageUsed').textContent = `${data.disk_used_display || ''}`.trim() ||
      (data.disk_total - data.disk_free).toLocaleString();
    document.getElementById('storageUsed').textContent = humanFromBytes(data.disk_total - data.disk_free);
    document.getElementById('storageFree').textContent = humanFromBytes(data.disk_free);
  } catch (err) {
    showToast('Could not load storage info', 'error');
  }
}

function humanFromBytes(n) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = n, i = 0;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return `${size.toFixed(1)} ${units[i]}`;
}

async function loadStatus() {
  const list = document.getElementById('statusList');
  try {
    const data = await api('/api/system/status');
    const items = [
      ['Server', data.server],
      ['Storage', data.storage],
      ['Database', data.database],
    ];
    list.innerHTML = items.map(([label, value]) => `
      <li><span class="status-dot"></span> ${label} <span class="status-value">${escapeHtml(value)}</span></li>
    `).join('');
  } catch (err) {
    list.innerHTML = '<li>Unable to load system status</li>';
  }
}

async function loadActivity() {
  const list = document.getElementById('activityList');
  try {
    const rows = await api('/api/me/activity?limit=8');
    if (!rows.length) {
      list.innerHTML = '<li class="empty-hint">No recent activity yet.</li>';
      return;
    }
    list.innerHTML = rows.map(r => `
      <li>
        <span class="activity-main">${escapeHtml(formatAction(r.action))}${r.target_id ? ': ' + escapeHtml(r.target_id) : ''}</span>
        <span>${escapeHtml(r.timestamp)}</span>
      </li>
    `).join('');
  } catch (err) {
    list.innerHTML = '<li class="empty-hint">Could not load recent activity.</li>';
  }
}

function formatAction(action) {
  return action.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase());
}
