import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCcw } from 'lucide-react';

import { Button } from './ui/Button';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * ErrorBoundary — top-level render-error guard.
 *
 * React swallows render-phase exceptions and unmounts the entire tree
 * by default, leaving the user with a blank page and no recovery path
 * other than a hard refresh. This boundary catches everything thrown
 * below it in the tree and shows a recovery card instead, so a bad
 * data shape from a backend response or a render-time library bug
 * can't take down the whole SPA.
 *
 * Scope: wraps the entire ``<main>`` block in App.tsx, so both the
 * landing page and the tool app are protected. Event handlers and
 * async code don't bubble through render, so this is not a substitute
 * for try/catch in hooks — it covers the uncontrolled-failure case
 * where a hook renders before its try/catch ran.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Log the full stack so devs see it in DevTools; the public UI
    // intentionally hides internals behind a generic message.
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] Caught render error:', error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ error: null });
    // Nudge the caller back to the landing view by clearing the hash
    // and reloading — full state reset is the safest recovery from an
    // unknown render-time shape mismatch.
    if (typeof window !== 'undefined' && window.location.hash) {
      window.location.hash = '';
    }
  };

  render() {
    if (this.state.error) {
      return (
        <div
          role="alert"
          className="min-h-screen flex items-center justify-center bg-background text-foreground p-6"
        >
          <div className="rm-box p-8 max-w-md w-full space-y-4 bg-card">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-8 h-8 text-destructive" aria-hidden="true" />
              <h1 className="text-2xl font-serif font-black tracking-tight">
                Algo salió mal
              </h1>
            </div>
            <p className="text-muted-foreground leading-relaxed">
              La aplicación encontró un error inesperado al renderizar esta
              vista. Tus datos locales están a salvo — sólo necesitás recargar
              para volver a la portada.
            </p>
            {import.meta.env.DEV && this.state.error && (
              <details className="text-xs font-mono bg-muted p-3 border-2 border-border">
                <summary className="cursor-pointer font-bold">
                  Detalle técnico (sólo dev)
                </summary>
                <pre className="mt-2 whitespace-pre-wrap break-words">
                  {this.state.error.message}
                </pre>
              </details>
            )}
            <Button
              variant="primary"
              size="md"
              onClick={this.handleReset}
              className="w-full"
            >
              <RefreshCcw className="w-4 h-4" aria-hidden="true" />
              Volver a la portada
            </Button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
