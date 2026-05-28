// Central API configuration for the v2 backend.
// Override at build/run time with VITE_API_BASE.
//
// IMPORTANT: the auth cookie is SameSite=Lax, so it is only sent when the page
// and the API are the SAME SITE. "localhost" and "127.0.0.1" count as different
// sites, so we derive the API host from the page host (window.location.hostname)
// to keep them aligned. This makes login work whether you open localhost:5173
// or 127.0.0.1:5173.
function resolveApiBase(): string {
  const override = (import.meta as any).env?.VITE_API_BASE;
  if (override) return override;
  const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
  return `http://${host}:8123`;
}

export const API_BASE: string = resolveApiBase();
