import { useState } from 'react';
import LandingPage from './LandingPage';
import ToolApp from './ToolApp';

export default function App() {
  const [view, setView] = useState<'landing' | 'tool'>('landing');

  return (
    <>
      {view === 'landing' ? (
        <LandingPage onStart={() => setView('tool')} />
      ) : (
        <ToolApp onBack={() => setView('landing')} />
      )}
    </>
  );
}
