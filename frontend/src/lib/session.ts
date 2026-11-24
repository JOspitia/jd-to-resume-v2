/**
 * session.ts — the "don't lose my work" persistence layer.
 *
 * The app used to keep every piece of state in React memory: the current
 * view (landing vs. tool), the form fields and the generated result. That
 * works until anything reloads the page — an F5, a restored tab, a
 * `target="_blank"` link that the embedded browser resolves in the SAME
 * tab (which is what the in-app browser does). When the SPA boots again,
 * `App.tsx` starts on the landing page and the whole session is gone:
 * the uploaded CV, the job description, the generated PDF, the YAML.
 *
 * These helpers persist that state in **sessionStorage**, not
 * localStorage:
 *
 *   * sessionStorage is scoped to the browser TAB, so a new tab starts
 *     clean — a stale CV from last week never shows up in a new visit.
 *   * It dies with the tab, which is exactly the lifetime we want for
 *     "the work I am doing right now".
 *
 * The contact URLs keep using localStorage (see `useProfile`): those ARE
 * a durable preference — the user expects to retype them never.
 *
 * Every function is wrapped in try/catch: sessionStorage throws in
 * private mode and when the quota is exceeded, and losing the
 * persistence layer must never break the app.
 */

const PREFIX = 'jd-to-resume.';

/** Reads and parses a session entry. Returns null when missing or corrupt. */
export function readSession<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(PREFIX + key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    // Corrupt entry or storage disabled — treat it as "nothing saved".
    return null;
  }
}

/** Serializes and stores a session entry. Silently no-ops when storage is unavailable. */
export function writeSession(key: string, value: unknown): void {
  try {
    sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Quota exceeded / private mode — persistence is best-effort.
  }
}

/** Removes a session entry. */
export function clearSession(key: string): void {
  try {
    sessionStorage.removeItem(PREFIX + key);
  } catch {
    // best-effort
  }
}
