/**
 * Shared API client — injects the JWT, logs out on 401, throws on error.
 *   const data = await api.get('/tenants/products');
 *   await api.post('/tenants/customers', { name: 'John' });
 */

const BASE = '/api';

export function getToken() {
  try { return localStorage.getItem('token'); } catch { return null; }
}

export function clearSession() {
  try {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
  } catch { /* storage unavailable */ }
}

async function request(method, path, body, { form = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
    payload = new URLSearchParams(body).toString();
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  const res = await fetch(`${BASE}${path}`, { method, headers, body: payload });

  if (res.status === 401 && token) {
    clearSession();
    window.location.href = '/login';
    return new Promise(() => {}); // navigation is underway
  }

  if (!res.ok) {
    let detail = `Request failed (HTTP ${res.status})`;
    try {
      const err = await res.json();
      if (typeof err.detail === 'string') detail = err.detail;
      else if (Array.isArray(err.detail)) detail = err.detail.map(d => d.msg).join('; ');
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }

  if (res.status === 204) return null;
  return res.json();
}

const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  postForm: (path, body) => request('POST', path, body, { form: true }),
  put: (path, body) => request('PUT', path, body),
  del: (path) => request('DELETE', path),
};

export default api;
