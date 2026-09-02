/**
 * Thin fetch wrapper used by every page. Throws an Error with a readable
 * message on non-2xx responses so callers can just try/catch.
 */
async function api(url, options = {}) {
  const opts = Object.assign({ headers: {} }, options);
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers['Content-Type'] = 'application/json';
  }

  if (opts.method && !['GET', 'HEAD', 'OPTIONS'].includes(opts.method.toUpperCase())) {
    const csrf = document.cookie.split('; ').find(row => row.startsWith('hs_csrf='));
    if (csrf) {
      opts.headers['X-CSRF-Token'] = decodeURIComponent(csrf.split('=')[1]);
    }
  }

  const res = await fetch(url, opts);

  if (res.status === 401) {
    window.location.href = '/login';
    throw new Error('Not authenticated');
  }

  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }

  if (!res.ok) {
    const message = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
}

function qs(name, fallback = '') {
  const params = new URLSearchParams(window.location.search);
  return params.get(name) || fallback;
}

function debounce(fn, wait = 300) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function timeAgo(unixSeconds) {
  const diff = Math.floor(Date.now() / 1000) - unixSeconds;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(unixSeconds * 1000).toLocaleDateString();
}

const FILE_ICONS = {
  document: '📄', image: '🖼', video: '🎬', audio: '🎵', archive: '🗄', other: '📁',
};
