(() => {
  let category = qs('category', 'photos');
  let items = [];
  let lightboxIndex = 0;

  const grid = document.getElementById('mediaGrid');
  const emptyState = document.getElementById('mediaEmptyState');

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.media-tab').forEach(tab => {
      if (tab.dataset.category === category) tab.classList.add('active');
      else tab.classList.remove('active');
      tab.addEventListener('click', () => {
        category = tab.dataset.category;
        document.querySelectorAll('.media-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        load();
      });
    });

    document.getElementById('lightboxClose').addEventListener('click', closeLightbox);
    document.getElementById('lightboxPrev').addEventListener('click', () => showLightbox(lightboxIndex - 1));
    document.getElementById('lightboxNext').addEventListener('click', () => showLightbox(lightboxIndex + 1));
    document.getElementById('videoClose').addEventListener('click', closeVideo);

    document.addEventListener('keydown', (e) => {
      const lightbox = document.getElementById('lightbox');
      if (!lightbox.hidden) {
        if (e.key === 'Escape') closeLightbox();
        if (e.key === 'ArrowLeft') showLightbox(lightboxIndex - 1);
        if (e.key === 'ArrowRight') showLightbox(lightboxIndex + 1);
      }
    });

    load();
  });

  async function load() {
    try {
      const data = await api(`/api/media?category=${encodeURIComponent(category)}&page_size=100`);
      items = data.items;
      renderGrid();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  function renderGrid() {
    if (!items.length) {
      grid.innerHTML = '';
      emptyState.hidden = false;
      return;
    }
    emptyState.hidden = true;

    if (category === 'audio') {
      grid.innerHTML = items.map((item, i) => `
        <div class="media-item audio-item" data-index="${i}">
          <span class="audio-glyph">♪</span>
          <div class="file-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
          <div class="file-meta">${escapeHtml(item.size_display)}</div>
        </div>`).join('');
      grid.querySelectorAll('.media-item').forEach(el => {
        el.addEventListener('click', () => playAudio(items[Number(el.dataset.index)]));
      });
      return;
    }

    if (category === 'videos') {
      grid.innerHTML = items.map((item, i) => `
        <div class="media-item" data-index="${i}">
          <img src="/api/media/${item.id}/thumbnail" alt="${escapeHtml(item.name)}" loading="lazy">
          <div class="media-name">${escapeHtml(item.name)}</div>
        </div>`).join('');
      grid.querySelectorAll('.media-item').forEach(el => {
        el.addEventListener('click', () => playVideo(items[Number(el.dataset.index)]));
      });
      return;
    }

    // photos + other
    grid.innerHTML = items.map((item, i) => `
      <div class="media-item" data-index="${i}">
        <img src="/api/media/${item.id}/thumbnail" alt="${escapeHtml(item.name)}" loading="lazy">
        <div class="media-name">${escapeHtml(item.name)}</div>
      </div>`).join('');
    grid.querySelectorAll('.media-item').forEach(el => {
      el.addEventListener('click', () => showLightbox(Number(el.dataset.index)));
    });
  }

  function showLightbox(index) {
    if (index < 0) index = items.length - 1;
    if (index >= items.length) index = 0;
    lightboxIndex = index;
    const item = items[index];
    document.getElementById('lightboxImage').src = `/api/media/${item.id}/stream`;
    document.getElementById('lightbox').hidden = false;
  }
  function closeLightbox() { document.getElementById('lightbox').hidden = true; }

  function playVideo(item) {
    const overlay = document.getElementById('videoOverlay');
    const player = document.getElementById('videoPlayer');
    player.src = `/api/media/${item.id}/stream`;
    document.getElementById('videoCaption').textContent = `${item.name} • ${item.size_display}`;
    overlay.hidden = false;
    player.play().catch(() => {});
  }
  function closeVideo() {
    const player = document.getElementById('videoPlayer');
    player.pause();
    player.removeAttribute('src');
    player.load();
    document.getElementById('videoOverlay').hidden = true;
  }

  function playAudio(item) {
    const bar = document.getElementById('audioPlayerBar');
    const player = document.getElementById('audioPlayer');
    player.src = `/api/media/${item.id}/stream`;
    document.getElementById('audioTrackName').textContent = item.name;
    bar.hidden = false;
    player.play().catch(() => {});
  }
})();
