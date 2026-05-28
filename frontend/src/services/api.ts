// Thin fetch wrapper for the v2 backend.
// - Prepends API_BASE.
// - Sends the HttpOnly auth cookie on every request (credentials: 'include').
// - Surfaces 401 to a global handler so the app can bounce to the login screen.
import { API_BASE } from './config';

type UnauthorizedHandler = () => void;

let onUnauthorized: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(fn: UnauthorizedHandler | null): void {
  onUnauthorized = fn;
}

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export interface ApiFetchOptions extends RequestInit {
  // When true (default), a 401 triggers the global unauthorized handler.
  bounceOn401?: boolean;
}

export async function apiFetch(path: string, opts: ApiFetchOptions = {}): Promise<Response> {
  const { bounceOn401 = true, headers, ...rest } = opts;
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;

  const res = await fetch(url, {
    credentials: 'include',
    headers: {
      ...(rest.body && !(rest.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...(headers ?? {}),
    },
    ...rest,
  });

  if (res.status === 401 && bounceOn401 && onUnauthorized) {
    onUnauthorized();
  }
  return res;
}

// Convenience: parse JSON, throw ApiError on non-2xx.
export async function apiJson<T = any>(path: string, opts: ApiFetchOptions = {}): Promise<T> {
  const res = await apiFetch(path, opts);
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const raw = (data && (data.detail || data.message || data.error)) || res.statusText;
    let message: string;
    if (typeof raw === 'string') {
      message = raw;
    } else if (Array.isArray(raw)) {
      // FastAPI/Pydantic 422: [{loc:[...,field], msg}, ...] -> "field: msg; ..."
      message = raw
        .map((e: any) => {
          const field = Array.isArray(e.loc) ? e.loc[e.loc.length - 1] : '';
          return field ? `${field}: ${e.msg}` : e.msg;
        })
        .join('; ');
    } else {
      message = JSON.stringify(raw);
    }
    throw new ApiError(res.status, message, data);
  }
  return data as T;
}
