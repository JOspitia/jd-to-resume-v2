import { useCallback, useState } from 'react';
import type { Profile } from './useProfile';
import type { Generation } from './useGeneration';
import { renderFromYaml } from '../lib/renderFromYaml';

/**
 * useRedesign — "change the design, keep the text".
 *
 * The generation pipeline rewrites the CV with the LLM every time it runs,
 * so changing the template meant re-running the model and getting different
 * wording back. This hook offers the alternative: re-render the YAML that
 * produced the PDF the user is currently looking at, with a different
 * template / accent, **without touching the LLM at all**.
 *
 * The endpoint used is `/api/render-from-yaml`, which parses the YAML it
 * receives and hands it straight to the renderer. Because the document is
 * the same one, the extracted text layer is byte-for-byte identical — only
 * the design changes.
 *
 * The selected design is written back to the profile so a later full
 * regeneration (with the LLM) keeps the same look.
 */

export type RedesignStatus = 'idle' | 'applying' | 'error';

type RedesignDeps = {
  profile: Pick<
    Profile,
    | 'selectedTheme'
    | 'accentColor'
    | 'fitSinglePage'
    | 'pageBreakSection'
    | 'jd'
    | 'domainGame'
    | 'photo'
    | 'setSelectedTheme'
    | 'setAccentColor'
  >;
  generation: Pick<
    Generation,
    'lastGeneratedYaml' | 'setDownloadUrl' | 'setGeneratedPdfFilename'
  >;
};

export function useRedesign({ profile, generation }: RedesignDeps) {
  const { lastGeneratedYaml, setDownloadUrl, setGeneratedPdfFilename } = generation;

  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<RedesignStatus>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  // Draft selections — only committed to the profile when the user applies.
  const [theme, setTheme] = useState(profile.selectedTheme);
  const [accent, setAccent] = useState(profile.accentColor);

  /** Opens the panel, seeding the draft with the design currently in use. */
  const openPanel = useCallback(() => {
    setTheme(profile.selectedTheme);
    setAccent(profile.accentColor);
    setErrorMessage('');
    setStatus('idle');
    setOpen(true);
  }, [profile.selectedTheme, profile.accentColor]);

  const closePanel = useCallback(() => {
    setOpen(false);
    setErrorMessage('');
    setStatus('idle');
  }, []);

  /**
   * Re-renders the current YAML with the drafted design and swaps the
   * preview / download links to the new PDF.
   */
  const apply = useCallback(async () => {
    if (!lastGeneratedYaml) {
      setStatus('error');
      setErrorMessage(
        'No hay un YAML guardado de este CV. Regenerá el CV una vez y después podrás cambiar solo el diseño.',
      );
      return;
    }

    setStatus('applying');
    setErrorMessage('');

    try {
      const result = await renderFromYaml({
        yaml: lastGeneratedYaml,
        theme,
        accent,
        fitSinglePage: profile.fitSinglePage,
        pageBreakSection: profile.pageBreakSection,
        jd: profile.jd,
        domainGame: profile.domainGame,
        photo: profile.photo,
      });

      setDownloadUrl(result.downloadUrl);
      setGeneratedPdfFilename(result.filename);
      // Keep the global selection in sync so a later full regeneration uses
      // the same design.
      profile.setSelectedTheme(theme);
      profile.setAccentColor(accent);
      setOpen(false);
      setStatus('idle');
    } catch (err: unknown) {
      const isAbort = err instanceof DOMException && err.name === 'AbortError';
      setStatus('error');
      setErrorMessage(
        isAbort
          ? 'El render agotó el tiempo de espera (1 min). Reintentá.'
          : err instanceof Error
            ? err.message
            : 'No se pudo aplicar el nuevo diseño.',
      );
    }
  }, [
    lastGeneratedYaml,
    theme,
    accent,
    profile,
    setDownloadUrl,
    setGeneratedPdfFilename,
  ]);

  return {
    open,
    status,
    errorMessage,
    theme,
    accent,
    setTheme,
    setAccent,
    openPanel,
    closePanel,
    apply,
    /** True when there is a YAML snapshot to re-render. */
    canRedesign: !!lastGeneratedYaml,
  };
}

export type Redesign = ReturnType<typeof useRedesign>;
