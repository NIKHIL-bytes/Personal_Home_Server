/**
 * In-browser file viewer, used by both "My Files" and "Shared Files".
 * Reuses the existing /view endpoints (which enforce the same auth/
 * ownership checks as everything else) — this file only decides which
 * HTML element to render for a given file, it never touches the
 * filesystem or bypasses any permission check itself.
 */
(() => {
  // Mirrors app/utils.py's preview_kind() classification. Kept as a small,
  // deliberate duplication — the server is still the source of truth and
  // enforces the same rule via /view; this only picks which player to draw.
  const KIND_EXT = {
    image: ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
    pdf: ['.pdf'],
    video: ['.mp4', '.webm', '.ogg'],
    audio: ['.mp3', '.wav', '.ogg'],
    text: ['.txt', '.md', '.csv', '.log'],
  };

  function extOf(name) {
    const i = name.lastIndexOf('.');
    return i === -1 ? '' : name.slice(i).toLowerCase();
  }

  function previewKind(name) {
    const ext = extOf(name);
    for (const kind in KIND_EXT) {
      if (KIND_EXT[kind].includes(ext)) return kind;
    }
    return 'unsupported';
  }

  let overlay = null;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'viewer-overlay';
    overlay.innerHTML = `
      <div class="viewer-panel">
        <div class="viewer-topbar">
          <button class="icon-btn viewer-close" aria-label="Close viewer" title="Close">←</button>
          <div class="viewer-filename"></div>
          <a class="btn btn-primary viewer-download" title="Download">⬇ Download</a>
        </div>
        <div class="viewer-body"></div>
      </div>`;
    document.body.appendChild(overlay);

    overlay.querySelector('.viewer-close').addEventListener('click', closeViewer);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeViewer();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && overlay.classList.contains('open')) closeViewer();
    });

    return overlay;
  }

  function closeViewer() {
    if (!overlay) return;
    overlay.classList.remove('open');
    // Clear the body so any playing <video>/<audio> stops immediately.
    overlay.querySelector('.viewer-body').innerHTML = '';
    document.body.classList.remove('viewer-open');
  }

  /**
   * Open the viewer for `item` (as returned by /api/files, /api/shared, or
   * the admin storage browser) from the given `scope`:
   *   'files'  -> personal files (My Files)
   *   'shared' -> shared storage
   *   'admin'  -> admin browsing a specific user's storage; pass the
   *               target user's id as `extraUserId`.
   */
  window.openViewer = function openViewer(item, scope, extraUserId) {
    const ov = ensureOverlay();
    const body = ov.querySelector('.viewer-body');
    const filenameEl = ov.querySelector('.viewer-filename');
    const downloadEl = ov.querySelector('.viewer-download');

    let base;
    if (scope === 'shared') base = '/api/shared';
    else if (scope === 'admin') base = `/api/admin/users/${extraUserId}/files`;
    else base = '/api/files';

    const viewUrl = `${base}/view?path=${encodeURIComponent(item.path)}`;
    const downloadUrl = `${base}/download?path=${encodeURIComponent(item.path)}`;

    filenameEl.textContent = item.name;
    filenameEl.title = item.name;
    downloadEl.href = downloadUrl;

    const kind = previewKind(item.name);
    body.innerHTML = '';
    body.className = `viewer-body viewer-body-${kind}`;

    if (kind === 'image') {
      const img = document.createElement('img');
      img.src = viewUrl;
      img.alt = item.name;
      img.className = 'viewer-image';
      body.appendChild(img);
    } else if (kind === 'pdf') {
      const iframe = document.createElement('iframe');
      iframe.src = viewUrl;
      iframe.className = 'viewer-pdf';
      iframe.title = item.name;
      body.appendChild(iframe);
    } else if (kind === 'video') {
      const video = document.createElement('video');
      video.src = viewUrl;
      video.controls = true;
      video.autoplay = false;
      video.className = 'viewer-video';
      body.appendChild(video);
    } else if (kind === 'audio') {
      const wrap = document.createElement('div');
      wrap.className = 'viewer-audio-wrap';
      const icon = document.createElement('div');
      icon.className = 'viewer-audio-icon';
      icon.textContent = '🎵';
      const audio = document.createElement('audio');
      audio.src = viewUrl;
      audio.controls = true;
      audio.className = 'viewer-audio';
      wrap.appendChild(icon);
      wrap.appendChild(audio);
      body.appendChild(wrap);
    } else if (kind === 'text') {
      const pre = document.createElement('pre');
      pre.className = 'viewer-text';
      pre.textContent = 'Loading…';
      body.appendChild(pre);
      fetch(viewUrl)
        .then((r) => {
          if (!r.ok) throw new Error('Failed to load file');
          return r.text();
        })
        .then((text) => {
          // textContent only -- never innerHTML -- so file contents can
          // never be interpreted as HTML/JS, no matter what they contain.
          pre.textContent = text;
        })
        .catch(() => {
          pre.textContent = 'Unable to load this file.';
        });
    } else {
      const icon = (typeof FILE_ICONS !== 'undefined' && FILE_ICONS[item.type]) || '📄';
      body.innerHTML = `
        <div class="viewer-unsupported">
          <div class="viewer-unsupported-icon">${icon}</div>
          <div class="viewer-unsupported-name">${escapeHtml(item.name)}</div>
          <div class="viewer-unsupported-meta">${item.size_display ? escapeHtml(item.size_display) : ''}</div>
          <p class="viewer-unsupported-text">Preview is not available for this file type.</p>
          <a class="btn btn-primary" href="${downloadUrl}">⬇ Download File</a>
        </div>`;
    }

    ov.classList.add('open');
    document.body.classList.add('viewer-open');
  };

  window.closeViewer = closeViewer;
})();
