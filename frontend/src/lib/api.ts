/**
 * API base URL configuration.
 *
 * The frontend used to hardcode ``http://localhost:8000`` in every
 * fetch call, which blocked any non-localhost deployment (Vercel,
 * Netlify, Render, a tunnel, or a reverse proxy in front of the
 * backend). This module centralises the URL so every call site can
 * resolve through one function.
 *
 * Configuration:
 *   * Set ``VITE_API_BASE_URL`` at build time (Vite reads it from
 *     ``.env`` or the shell). Production deployments point this at
 *     the backend's public URL.
 *   * Empty string (default) → fetch hits the same origin. Use this
 *     when the backend is served behind a reverse proxy on the same
 *     domain as the frontend.
 *   * In development without the env var, we fall back to
 *     ``http://localhost:8000`` so the existing ``npm run dev`` /
 *     ``uvicorn main:app`` workflow keeps working out of the box.
 */

const DEV_FALLBACK = 'http://localhost:8000';

function readBase(): string {
  const raw = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
  const trimmed = raw.trim();
  if (trimmed) return trimmed;
  return import.meta.env.DEV ? DEV_FALLBACK : '';
}

export const API_BASE: string = readBase();

/**
 * Resolve a path against the configured API base.
 *
 * Accepts:
 *   * Absolute URLs (``https://x/y``) — returned unchanged. Useful
 *     for download URLs that the backend may decide to redirect to
 *     a CDN.
 *   * Paths starting with ``/`` — joined to the base without doubling
 *     the slash.
 *   * Paths without leading ``/`` — joined with one inserted.
 *
 * Examples (with empty ``API_BASE`` for prod same-origin):
 *   * ``apiUrl('/api/clear-cache')`` → ``'/api/clear-cache'``
 *   * ``apiUrl('api/clear-cache')``  → ``'/api/clear-cache'``
 *   * ``apiUrl('https://cdn/x.pdf')`` → ``'https://cdn/x.pdf'``
 *
 * With ``VITE_API_BASE_URL=http://localhost:8000``:
 *   * ``apiUrl('/api/clear-cache')`` → ``'http://localhost:8000/api/clear-cache'``
 */
export function apiUrl(path: string): string {
  if (!path) return API_BASE;
  if (/^https?:\/\//i.test(path)) return path;
  const base = API_BASE.endsWith('/') ? API_BASE.slice(0, -1) : API_BASE;
  const tail = path.startsWith('/') ? path : `/${path}`;
  return `${base}${tail}`;
}
