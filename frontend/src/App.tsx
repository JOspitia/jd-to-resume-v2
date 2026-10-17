import { useState } from 'react';
import LandingPage from './LandingPage';
import ToolApp from './ToolApp';
import { ErrorBoundary } from './components/ErrorBoundary';

export default function App() {
  const [view, setView] = useState<'landing' | 'tool'>('landing');

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
