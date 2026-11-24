/**
 * pdf.ts — download and preview helpers that never navigate the app away.
 *
 * Why this module exists
 * ----------------------
 * The download / preview buttons used to be plain `<a href>` tags with
 * `target="_blank"`. In a normal desktop browser that opens a second tab
 * and everything is fine. In an **embedded browser** (the in-app browser
 * panel, Electron, some kiosk shells) `_blank` is resolved in the SAME
 * tab: the SPA is replaced by the PDF viewer, and when the user comes
 * back the app reloads from scratch — landing page, empty form, lost
 * result.
 *
 * The fix is to stop using navigation as a download mechanism:
 *
 *   * Download → fetch the bytes, wrap them in a Blob and hand them to a
 *     temporary `<a download>`. The browser saves the file; the page
 *     never moves.
 *   * Preview → render the Blob in an `<iframe>` inside the app (see
 *     `PdfPreviewModal`), so the user keeps the form next to the PDF.
 *
 * Both need CORS: the frontend talks to the backend on another origin
 * during development. The backend already allows the Vite dev origins
 * (`CORS_ALLOWED_ORIGINS`), and in a same-origin production deployment
 * this is a no-op. When the fetch fails anyway (a deployment with a
 * misconfigured CORS list), every helper degrades to opening the URL in
 * a new tab instead of failing outright.
 */

/** Fetches a PDF as a Blob. Throws when the request fails. */
export async function fetchPdfBlob(url: string, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(url, {
    headers: { Accept: 'application/pdf' },
    signal,
  });
  if (!response.ok) {
    throw new Error(`No se pudo cargar el PDF (HTTP ${response.status}).`);
  }
  return response.blob();
}

/**
 * Saves the PDF to the user's disk without navigating the page.
 *
 * @param url     absolute or relative URL of the PDF.
 * @param filename name the browser should give the saved file.
 */
export async function downloadPdf(url: string, filename: string): Promise<void> {
  const blob = await fetchPdfBlob(url);
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  // Revoking immediately can cancel the download in some browsers; give
  // it a tick to start.
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
}

/**
 * Opens the PDF in a separate browser tab, leaving the app untouched.
 * Used as the explicit escape hatch inside the preview modal.
 */
export function openPdfInNewTab(url: string): boolean {
  const opened = window.open(url, '_blank', 'noopener,noreferrer');
  return opened !== null;
}

/**
 * Best-effort download: if the Blob fetch fails (CORS misconfigured,
 * network hiccup), fall back to opening the URL in a new tab rather than
 * leaving the user with a dead button.
 */
export async function downloadPdfOrOpen(url: string, filename: string): Promise<boolean> {
  try {
    await downloadPdf(url, filename);
    return true;
  } catch (error) {
    console.warn('No se pudo descargar el PDF sin navegar; se abre en otra pestaña.', error);
    openPdfInNewTab(url);
    return false;
  }
}
