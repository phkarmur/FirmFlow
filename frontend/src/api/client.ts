function getCsrfToken(): string {
  const name = 'csrftoken';
  if (!document.cookie) return '';
  for (const part of document.cookie.split(';')) {
    const cookie = part.trim();
    if (cookie.startsWith(name + '=')) {
      return decodeURIComponent(cookie.substring(name.length + 1));
    }
  }
  return '';
}

/** Event fired when the server says the session is gone (401 / 403 "not authenticated"). */
export const SESSION_EXPIRED_EVENT = 'firmflow:session-expired';

export interface ApiError {
  status: number;
  requestId: string | null;
  [key: string]: any;
}

export async function apiRequest<T = any>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = endpoint.startsWith('/') ? endpoint : `/api/v1/${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  const method = (options.method || 'GET').toUpperCase();
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrf = getCsrfToken();
    if (csrf) headers.set('X-CSRFToken', csrf);
  }

  const response = await fetch(url, { ...options, headers, credentials: 'include' });
  const requestId = response.headers.get('X-Request-ID');

  if (!response.ok) {
    let errorData: any;
    try {
      errorData = await response.json();
    } catch {
      errorData = { error: response.statusText || `HTTP ${response.status}` };
    }
    if (typeof errorData !== 'object' || errorData === null || Array.isArray(errorData)) {
      errorData = { error: String(errorData) };
    }
    const err: ApiError = { ...errorData, status: response.status, requestId };
    // Log with the request id so a screenshot can be matched to server logs (spec §10)
    console.warn(`[api] ${method} ${url} -> ${response.status}`, { requestId, error: errorData });
    const notAuthenticated =
      response.status === 401 ||
      (response.status === 403 && /credentials were not provided|not authenticated/i.test(String(errorData.detail || '')));
    if (notAuthenticated && !url.includes('/auth/me/') && !url.includes('/auth/login/')) {
      window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
    }
    throw err;
  }

  if (response.status === 204) return {} as T;
  const type = response.headers.get('Content-Type') || '';
  if (!type.includes('application/json')) return (await response.text()) as unknown as T;
  return response.json();
}

export const api = {
  get: <T = any>(url: string) => apiRequest<T>(url, { method: 'GET' }),
  post: <T = any>(url: string, data?: any) =>
    apiRequest<T>(url, { method: 'POST', body: data instanceof FormData ? data : JSON.stringify(data || {}) }),
  patch: <T = any>(url: string, data?: any) =>
    apiRequest<T>(url, { method: 'PATCH', body: data instanceof FormData ? data : JSON.stringify(data || {}) }),
  delete: <T = any>(url: string, data?: any) =>
    apiRequest<T>(url, { method: 'DELETE', body: data ? JSON.stringify(data) : undefined }),
};

/**
 * Turn any API error into one readable sentence.
 * Handles {error}, {detail}, {field: [msg]}, {completion_blocked: [...]}, nested lists.
 */
export function errorMessage(err: any, fallback = 'Something went wrong. Please try again.'): string {
  if (!err) return fallback;
  if (typeof err === 'string') return err;
  if (err instanceof Error) return err.message || fallback;
  if (err.completion_blocked) {
    return `Cannot complete yet: ${([] as string[]).concat(err.completion_blocked).join('; ')}`;
  }
  if (err.error) return flatten(err.error);
  if (err.detail) return flatten(err.detail);
  const parts: string[] = [];
  for (const [key, value] of Object.entries(err)) {
    if (key === 'status' || key === 'requestId') continue;
    const label = key === 'non_field_errors' ? '' : `${key.replace(/_/g, ' ')}: `;
    parts.push(label + flatten(value));
  }
  return parts.length ? parts.join(' · ') : fallback;
}

function flatten(value: any): string {
  if (value == null) return '';
  if (Array.isArray(value)) return value.map(flatten).join('; ');
  if (typeof value === 'object') return Object.values(value).map(flatten).join('; ');
  return String(value);
}

/** Today's date as YYYY-MM-DD in the browser's local time (not UTC). */
export function localToday(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** Fetch every page of a paginated list endpoint (use only for small lists, e.g. staff). */
export async function fetchAllPages<T = any>(url: string, maxPages = 20): Promise<T[]> {
  const out: T[] = [];
  let next: string | null = url + (url.includes('?') ? '&' : '?') + 'page_size=500';
  let pages = 0;
  while (next && pages < maxPages) {
    const res: any = await api.get(next);
    if (Array.isArray(res)) return res;
    out.push(...(res.results || []));
    next = res.next ? new URL(res.next, window.location.origin).pathname + new URL(res.next, window.location.origin).search : null;
    pages += 1;
  }
  return out;
}
