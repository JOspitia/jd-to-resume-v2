import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Download, ExternalLink, Loader2, X } from 'lucide-react';

import { Button } from './ui/Button';
import { downloadPdfOrOpen, fetchPdfBlob, openPdfInNewTab } from '../lib/pdf';

/**
 * PdfPreviewModal — shows the generated PDF **inside the app**.
 *
 * Why this exists
 * ---------------
 * "Preview" used to be an `<a href="…?inline=1" target="_blank">`. In a
 * desktop browser that opens a second tab and the app survives. In an
 * embedded browser (the in-app browser panel, Electron) `_blank` is
 * resolved in the SAME tab: the whole SPA is replaced by the PDF viewer,
 * and coming back reloads the app from scratch — which used to land the
 * user on the landing page with an empty form.
 *
 * This modal renders the PDF in an `<iframe>` over the app, so the user
 * can read the result and keep editing the inputs at the same time.
 *
 * The PDF is fetched as a Blob and shown through an object URL: a Blob
 * URL is same-origin, so the browser's PDF viewer always renders it,
 * regardless of how the backend is hosted. If the fetch fails (a
 * deployment with a misconfigured CORS allow-list), the modal falls back
 * to embedding the URL directly and offers "Abrir en otra pestaña".
 */

export type PdfPreviewModalProps = {
  /** URL of the PDF (absolute, or a path the caller resolved). */
  url: string;
  /** File name used by the download button. */
  filename: string;
  /** Heading shown in the modal header. */
  title: string;
  /** Called when the user closes the modal. */
  onClose: () => void;
};

export function PdfPreviewModal({ url, filename, title, onClose }: PdfPreviewModalProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Direct URL with `inline=1` so the browser renders it instead of
  // treating the navigation as a download. Used as the fallback when the
  // Blob fetch is not possible.
  const inlineUrl = `${url}${url.includes('?') ? '&' : '?'}inline=1`;

  useEffect(() => {
    let cancelled = false;
    let created: string | null = null;
    // The controller lets the cleanup abort the request: React's StrictMode
    // mounts the effect twice in development, and without this the PDF
    // would be downloaded twice.
    const controller = new AbortController();

    (async () => {
      try {
        const blob = await fetchPdfBlob(url, controller.signal);
        if (cancelled) return;
        created = URL.createObjectURL(blob);
        setObjectUrl(created);
      } catch (error) {
        if (cancelled) return;
        console.warn('No se pudo cargar el PDF en el visor embebido.', error);
        setFailed(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
      if (created) URL.revokeObjectURL(created);
    };
  }, [url]);

  // Escape closes the modal.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  // The modal covers the page: stop the body from scrolling behind it.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pdf-preview-title"
      onClick={(event) => {
        // Click on the backdrop (not on the panel) closes the modal.
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="flex flex-col w-full max-w-5xl h-[92vh] bg-card border-4 border-border shadow-neo-lg">
        <div className="flex items-center justify-between gap-3 p-4 border-b-4 border-border bg-muted">
          <h2
            id="pdf-preview-title"
            className="text-lg md:text-xl font-extrabold font-serif text-foreground truncate"
          >
            {title}
          </h2>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void downloadPdfOrOpen(url, filename)}
              aria-label={`Descargar ${filename}`}
            >
              <Download className="w-4 h-4" aria-hidden="true" /> Descargar
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => openPdfInNewTab(inlineUrl)}
              aria-label="Abrir el PDF en otra pestaña"
            >
              <ExternalLink className="w-4 h-4" aria-hidden="true" /> Otra pestaña
            </Button>
            <Button
              ref={closeRef}
              variant="outline"
              size="sm"
              onClick={onClose}
              aria-label="Cerrar la previsualización"
            >
              <X className="w-4 h-4" aria-hidden="true" /> Cerrar
            </Button>
          </div>
        </div>

        <div className="relative flex-1 min-h-0 bg-background">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center gap-3 text-muted-foreground">
              <Loader2 className="w-6 h-6 animate-spin" aria-hidden="true" />
              <span className="font-mono text-sm">Cargando el PDF…</span>
            </div>
          )}
          {failed && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
              <p className="font-mono text-sm text-muted-foreground">
                No se pudo mostrar el PDF dentro de la app (la vista embebida no está
                disponible). Abrilo en otra pestaña o descargalo.
              </p>
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => openPdfInNewTab(inlineUrl)}
                >
                  <ExternalLink className="w-4 h-4" aria-hidden="true" /> Abrir en otra pestaña
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void downloadPdfOrOpen(url, filename)}
                >
                  <Download className="w-4 h-4" aria-hidden="true" /> Descargar
                </Button>
              </div>
            </div>
          )}
          {!failed && objectUrl && (
            <iframe
              src={objectUrl}
              title={title}
              className="w-full h-full border-0"
            />
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

export default PdfPreviewModal;
