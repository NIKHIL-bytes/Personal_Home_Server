document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const scrim = document.getElementById('sidebarScrim');
  const menuToggle = document.getElementById('menuToggle');

  function closeSidebar() {
    sidebar && sidebar.classList.remove('open');
    scrim && scrim.classList.remove('open');
  }

  if (menuToggle) {
    menuToggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      scrim.classList.toggle('open');
    });
  }
  if (scrim) scrim.addEventListener('click', closeSidebar);

  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      try {
        await api('/api/auth/logout', { method: 'POST' });
      } catch (err) { /* ignore */ }
      window.location.href = '/login';
    });
  }

  const globalSearch = document.getElementById('globalSearch');
  if (globalSearch) {
    globalSearch.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && globalSearch.value.trim()) {
        window.location.href = `/files?q=${encodeURIComponent(globalSearch.value.trim())}`;
      }
    });
  }
});
