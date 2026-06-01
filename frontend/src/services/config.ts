// Central API base URL. Empty string by default → all calls are RELATIVE
// (`/api/...`, `/auth/...`). The Vite dev server (vite.config.ts → server.proxy)
// forwards them to the backend, so the backend's port and host live in exactly
// one place: VITE_API_TARGET in .env. In production, your reverse proxy
// (nginx / CDN / platform) does the same forwarding.
//
// Override with VITE_API_BASE when the frontend is deployed on a different
// origin than the API and you can't (or don't want to) proxy:
//   VITE_API_BASE=https://api.example.com npm run build
// In that case the backend MUST run on HTTPS and set CORS + a SameSite=None
// Secure cookie. See README.
export const API_BASE: string =
  ((import.meta as any).env?.VITE_API_BASE as string | undefined) ?? '';
