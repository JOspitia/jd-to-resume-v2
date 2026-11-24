import { useEffect, useState } from 'react';
import LandingPage from './LandingPage';
import ToolApp from './ToolApp';
import { ErrorBoundary } from './components/ErrorBoundary';
import { readSession, writeSession } from './lib/session';

/**
 * App — the landing/tool switch.
 *
 * The active view used to live only in React state, so any reload of the
 * SPA sent the user back to the landing page and threw away the whole
 * session (uploaded CV, job description, generated PDF). That was very
 * visible in the embedded browser, where the "Preview" link resolves in
 * the same tab: the app is replaced by the PDF viewer and, on the way
 * back, the SPA reboots.
 *
 * The view is now persisted in sessionStorage, so a reload lands the user
 * back in the tool where they were. sessionStorage is per-tab, so a
 * brand-new tab still starts on the landing page.
 */

const VIEW_SESSION_KEY = 'view';

type View = 'landing' | 'tool';

export default function App() {
  const [view, setView] = useState<View>(() => {
    const saved = readSession<View>(VIEW_SESSION_KEY);
    return saved === 'tool' ? 'tool' : 'landing';
  });

  useEffect(() => {
    writeSession(VIEW_SESSION_KEY, view);
  }, [view]);

  return (
    <>
      {/* Skip link — first focusable element in the DOM for keyboard users.
          CSS `.skip-link` (in index.css) hides it off-screen until it
          receives focus, then snaps it to the top-left corner. Lands focus
          on #main-content which wraps the active view. */}
      <a href="#main-content" className="skip-link">
        Saltar al contenido principal
      </a>
      <ErrorBoundary>
        <main id="main-content">
          {view === 'landing' ? (
            <LandingPage onStart={() => setView('tool')} />
          ) : (
            <ToolApp onBack={() => setView('landing')} />
          )}
        </main>
      </ErrorBoundary>
    </>
  );
}
