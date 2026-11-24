/* Admin API client: normal app login + admin-only endpoints.
   访问令牌只放在 sessionStorage，刷新页面需要重新登录或由 refresh token 续期。 */

const ACCESS_KEY = 'rongxing.admin.access';
const REFRESH_KEY = 'rongxing.admin.refresh';

export class ApiError extends Error {
  constructor(message, status = 0, code = 'NETWORK_ERROR') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

let refreshPromise = null;

function read(key) {
  try { return sessionStorage.getItem(key) || ''; } catch { return ''; }
}

function write(key, value) {
  try {
    if (value) sessionStorage.setItem(key, value);
    else sessionStorage.removeItem(key);
  } catch { /* private mode: keep the in-memory flow working for this page */ }
}

export function hasSession() {
  return Boolean(read(ACCESS_KEY));
}

export function clearSession() {
  write(ACCESS_KEY, '');
  write(REFRESH_KEY, '');
}

function announceExpired(message) {
  window.dispatchEvent(new CustomEvent('admin:session-expired', { detail: message }));
}

async function readPayload(response) {
  const text = await response.text();
  if (!text) return {};
  try { return JSON.parse(text); } catch { return { message: text.slice(0, 200) }; }
}

async function raw(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const token = read(ACCESS_KEY);
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('无法连接到绒星 API，请确认后端已启动。', 0, 'NETWORK_ERROR');
  }
  const payload = await readPayload(response);
  if (!response.ok) {
    throw new ApiError(payload.message || `请求失败（HTTP ${response.status}）`,
      response.status, payload.code || 'HTTP_ERROR');
  }
  return payload;
}

async function refreshTokens() {
  const token = read(REFRESH_KEY);
  if (!token) throw new ApiError('会话已失效，请重新登录', 401, 'TOKEN_EXPIRED');
  const pair = await raw('/auth/refresh', {
    method: 'POST', auth: false, body: { refresh_token: token },
  });
  write(ACCESS_KEY, pair.access_token);
  write(REFRESH_KEY, pair.refresh_token);
  return pair;
}

export async function call(path, options = {}) {
  try {
    return await raw(path, options);
  } catch (error) {
    const retryable = error instanceof ApiError && error.status === 401
      && !path.startsWith('/auth/');
    if (!retryable) throw error;
    if (!refreshPromise) {
      refreshPromise = refreshTokens().finally(() => { refreshPromise = null; });
    }
    try {
      await refreshPromise;
    } catch (refreshError) {
      clearSession();
      announceExpired('登录已过期，请重新登录。');
      throw refreshError;
    }
    return raw(path, options);
  }
}

function query(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

export const adminApi = {
  async login(email, password) {
    const pair = await raw('/auth/login', {
      method: 'POST', auth: false, body: { email, password },
    });
    write(ACCESS_KEY, pair.access_token);
    write(REFRESH_KEY, pair.refresh_token);
    return pair;
  },
  logout() {
    clearSession();
  },
  session() {
    return call('/admin/session');
  },
  overview(days) {
    return call(`/admin/overview${query({ days })}`);
  },
  users(params) {
    return call(`/admin/users${query(params)}`);
  },
  user(id) {
    return call(`/admin/users/${encodeURIComponent(id)}`);
  },
  setUserStatus(id, status) {
    return call(`/admin/users/${encodeURIComponent(id)}/status`, {
      method: 'PATCH', body: { status },
    });
  },
  pets(params) {
    return call(`/admin/pets${query(params)}`);
  },
  screenings(params) {
    return call(`/admin/screenings${query(params)}`);
  },
  screening(id) {
    return call(`/admin/screenings/${encodeURIComponent(id)}`);
  },
  aiUsage(days) {
    return call(`/admin/ai-usage${query({ days })}`);
  },
  audit(params) {
    return call(`/admin/audit${query(params)}`);
  },
};
