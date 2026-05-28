// Auth API wrappers. Cookie-based: the backend sets an HttpOnly auth_token
// cookie on login, so the browser carries it automatically on every request.
import { apiFetch, apiJson } from './api';

export interface AuthUser {
  id: number;
  username: string;
}

export async function register(username: string, password: string): Promise<AuthUser> {
  return apiJson<AuthUser>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
    bounceOn401: false,
  });
}

export async function login(username: string, password: string): Promise<void> {
  // Response body also carries access_token for non-cookie clients; we ignore it
  // and rely on the cookie.
  await apiJson('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
    bounceOn401: false,
  });
}

export async function logout(): Promise<void> {
  await apiFetch('/auth/logout', { method: 'POST', bounceOn401: false });
}

// Returns the current user if the session cookie is valid, else null.
export async function me(): Promise<AuthUser | null> {
  const res = await apiFetch('/auth/me', { bounceOn401: false });
  if (!res.ok) return null;
  return (await res.json()) as AuthUser;
}
