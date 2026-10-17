import { useCallback, useEffect, useState } from 'react';

/**
 * useTheme — PR6 dark mode hook.
 *
 * Manages the user's theme preference with three sources of truth, in
 * priority order:
 *
 *   1. localStorage('theme') — explicit user choice (light/dark).
 *   2. window.matchMedia('(prefers-color-scheme: dark)') — OS preference
 *      when no explicit choice has been made.
 *   3. Default 'light' — fallback when neither is available (SSR / older
 *      browsers).
 *
 * Side effects on change:
 *   - document.documentElement.classList.toggle('dark', theme === 'dark')
 *     so the .dark CSS selectors from index.css take over.
 *   - data-theme="light|dark" attribute for CSS attribute queries.
 *   - localStorage('theme', value) so reloads remember the choice.
 *
 * Listens for OS-level theme changes when the user hasn't explicitly
 * picked (no localStorage entry) — so a user with light OS preference
 * sees the app follow when their OS switches to dark automatically.
 */

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'theme';

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light';
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark') return stored;
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }
  return 'light';
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  // Apply the theme to <html> + persist whenever it changes.
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    root.setAttribute('data-theme', theme);
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // localStorage may be disabled (Safari private mode, etc.).
      // The theme still applies to the current session.
    }
  }, [theme]);

  // Follow the OS preference only when the user hasn't picked one yet.
  // If they explicitly chose light/dark, ignore future OS changes.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (window.localStorage.getItem(STORAGE_KEY) !== null) return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      setTheme(e.matches ? 'dark' : 'light');
    };
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);

  const setThemeExplicit = useCallback((next: Theme) => {
    setTheme(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  }, []);

  return {
    theme,
    setTheme: setThemeExplicit,
    toggleTheme,
  };
}