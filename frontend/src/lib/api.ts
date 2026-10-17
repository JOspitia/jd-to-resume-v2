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

/** Default ceiling for one-shot JSON endpoints (analyze-ats, render-from-yaml). */
export const DEFAULT_FETCH_TIMEOUT_MS = 60_000;
/** Longer ceiling for SSE pipelines that stream the full PDF (generate). */
export const SSE_FETCH_TIMEOUT_MS = 120_000;

/**
 * Wrap ``fetch`` with an ``AbortController`` that fires after
 * ``timeoutMs`` and returns whatever the caller passes in via
 * ``options``. The timer is always cleared in the ``finally`` block
 * so successful requests don't leak pending timers.
 *
 * The thrown error on timeout is a ``DOMException`` whose ``name`` is
 * ``"AbortError"`` — handlers can branch on that to render a friendly
 * message.
 *
 * Usage:
 *
 *   const controller = new AbortController();
 *   const res = await fetchWithTimeout('/api/x', { method: 'POST' });
 *   // ... or for SSE:
 *   const res = await fetchWithTimeout('/api/generate', { ... },
 *                                      SSE_FETCH_TIMEOUT_MS);
 */
export async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = DEFAULT_FETCH_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}
