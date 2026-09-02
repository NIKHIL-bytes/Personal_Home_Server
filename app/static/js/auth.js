document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('loginForm');
  const errorEl = document.getElementById('loginError');
  const submitBtn = document.getElementById('loginSubmit');
  const toggleBtn = document.getElementById('togglePassword');
  const passwordInput = document.getElementById('password');

  toggleBtn.addEventListener('click', () => {
    const isPassword = passwordInput.type === 'password';
    passwordInput.type = isPassword ? 'text' : 'password';
    toggleBtn.textContent = isPassword ? '🙈' : '👁';
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorEl.hidden = true;
    submitBtn.disabled = true;
    submitBtn.querySelector('.btn-label').style.visibility = 'hidden';
    submitBtn.querySelector('.btn-spinner').hidden = false;

    const username = document.getElementById('username').value.trim();
    const password = passwordInput.value;

    try {
      const csrf = document.cookie.split('; ').find(row => row.startsWith('hs_csrf='));
      const csrfToken = csrf ? decodeURIComponent(csrf.split('=')[1]) : '';

      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken
        },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Sign in failed');
      window.location.href = '/';
    } catch (err) {
      errorEl.textContent = err.message || 'Invalid username or password';
      errorEl.hidden = false;
      submitBtn.disabled = false;
      submitBtn.querySelector('.btn-label').style.visibility = 'visible';
      submitBtn.querySelector('.btn-spinner').hidden = true;
    }
  });
});
