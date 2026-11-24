import { useEffect, useState } from 'react';

import { apiUrl } from '../lib/api';
import { readSession, writeSession, clearSession } from '../lib/session';
import type { Profile } from './useProfile';
import type { CoverLetter } from '../types/coverLetter';

/**
 * useCoverLetter — owns the `POST /api/cover-letter` pipeline.
 *
 * Same shape as `useAudit` / `useGeneration`: a status machine, the
 * payload, an error message, and the two actions the letter needs
 * (copy to clipboard, download as a text file).
 *
 * The letter is a plain-text deliverable, not a PDF: the ATS portals
 * (Computrabajo, LinkedIn, Indeed) take a cover letter as a text field,
 * and a candidate usually pastes it into a form. The `.txt` download is
 * there for the cases where a file is expected instead.
 */

export type CoverLetterStatus = 'idle' | 'generating' | 'success' | 'error';

/**
 * The generated letter is persisted in sessionStorage under this key, so a
 * reload of the SPA keeps the letter on screen (and copyable) instead of
 * dropping the user back to an empty form.
 */
const LETTER_SESSION_KEY = 'cover-letter';

type CoverLetterDeps = {
  profile: Pick<
    Profile,
    | 'file'
    | 'jd'
    | 'targetRole'
    | 'domainGame'
    | 'companyName'
    | 'coverLetterTone'
    | 'coverLetterLength'
    | 'coverLetterLanguage'
    | 'letterStyle'
    | 'letterAccent'
    | 'linkedinUrl'
    | 'githubUrl'
    | 'portfolioUrl'
    | 'customPrompt'
  >;
};

/**
 * Pulls a human-readable message out of the backend's error envelope.
 * The API returns `detail` as a string (422/429) or as an object with an
 * `error` key (500/502), so both shapes have to be handled.
 */
function extractErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object') {
    const error = (detail as { error?: unknown }).error;
    if (typeof error === 'string' && error.trim()) return error;
  }
  return fallback;
}

export function useCoverLetter({ profile }: CoverLetterDeps) {
  const {
    file,
    jd,
    targetRole,
    domainGame,
    companyName,
    coverLetterTone,
    coverLetterLength,
    coverLetterLanguage,
    letterStyle,
    letterAccent,
    linkedinUrl,
    githubUrl,
    portfolioUrl,
    customPrompt,
  } = profile;

  /**
   * The generated letter is restored from sessionStorage on mount.
   *
   * The snapshot is read ONCE and used as the initial value of the state
   * (instead of restoring it in an effect): the first render already shows
   * the letter, so a reload does not wipe it.
   */
  const [savedLetter] = useState<CoverLetter | null>(() =>
    readSession<CoverLetter>(LETTER_SESSION_KEY),
  );
  const restoredLetter =
    savedLetter && typeof savedLetter.plain_text === 'string' ? savedLetter : null;

  const [status, setStatus] = useState<CoverLetterStatus>(() =>
    restoredLetter ? 'success' : 'idle',
  );
  const [letter, setLetter] = useState<CoverLetter | null>(() => restoredLetter);
  const [errorMessage, setErrorMessage] = useState('');
  const [copied, setCopied] = useState(false);

  // Live timer for the "en curso" surface (same pattern as useGeneration).
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (status !== 'generating') {
      setElapsedSeconds(0);
      return;
    }
    const interval = setInterval(() => setElapsedSeconds((prev) => prev + 1), 1000);
    return () => clearInterval(interval);
  }, [status]);

  // === Session persistence (reload-safe letter) ===
  useEffect(() => {
    if (status === 'success' && letter) {
      writeSession(LETTER_SESSION_KEY, letter);
    } else {
      clearSession(LETTER_SESSION_KEY);
    }
  }, [status, letter]);

  const reset = () => {
    setStatus('idle');
    setLetter(null);
    setErrorMessage('');
    setCopied(false);
    clearSession(LETTER_SESSION_KEY);
  };

  const handleGenerate = async () => {
    if (!file) {
      setErrorMessage('Seleccioná un archivo PDF de currículum.');
      setStatus('error');
      return;
    }

    setStatus('generating');
    setErrorMessage('');
    setCopied(false);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('jd', jd || '');
    formData.append('domain_game', domainGame);
    formData.append('target_role', targetRole || '');
    formData.append('company_name', companyName || '');
    formData.append('tone', coverLetterTone);
    formData.append('length', coverLetterLength);
    formData.append('language', coverLetterLanguage);
    formData.append('letter_style', letterStyle);
    formData.append('accent', letterAccent);
    // The profile links: whatever the user typed in the form wins over
    // what the PDF extraction found. They end up in the letterhead and
    // in the signature.
    formData.append('linkedin_url', linkedinUrl || '');
    formData.append('github_url', githubUrl || '');
    formData.append('portfolio_url', portfolioUrl || '');
    formData.append('custom_instructions', customPrompt || '');

    // The letter is a single LLM round-trip; 90s is a generous ceiling
    // (the CV pipeline gets 120s because it renders a PDF afterwards).
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 90_000);

    try {
      const response = await fetch(apiUrl('/api/cover-letter'), {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });

      if (!response.ok) {
        let payload: unknown = null;
        try {
          payload = await response.json();
        } catch {
          payload = null;
        }
        setErrorMessage(
          extractErrorMessage(
            payload,
            response.status === 429
              ? 'Demasiadas solicitudes seguidas. Esperá un minuto e intentá de nuevo.'
              : 'No se pudo generar la carta de presentación.',
          ),
        );
        setStatus('error');
        return;
      }

      const data = (await response.json()) as CoverLetter;
      setLetter(data);
      setStatus('success');
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        setErrorMessage('La generación tardó demasiado y se canceló. Probá de nuevo.');
      } else {
        setErrorMessage(
          err instanceof Error ? err.message : 'Ocurrió un error inesperado.',
        );
      }
      setStatus('error');
    } finally {
      clearTimeout(timeoutId);
    }
  };

  /** Copies the assembled letter to the clipboard. */
  const handleCopy = async () => {
    if (!letter) return;
    try {
      await navigator.clipboard.writeText(letter.plain_text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setErrorMessage(
        'El navegador no permitió copiar. Seleccioná el texto y copialo manualmente.',
      );
    }
  };

  /** Downloads the letter as a UTF-8 .txt file. */
  const handleDownload = () => {
    if (!letter) return;
    const blob = new Blob([letter.plain_text], {
      type: 'text/plain;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const company = companyName.trim().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-');
    const role = targetRole.trim().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-');
    const parts = ['carta-de-presentacion'];
    if (role) parts.push(role);
    if (company) parts.push(company);
    link.href = url;
    link.download = `${parts.join('-').toLowerCase() || 'carta-de-presentacion'}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return {
    status,
    letter,
    errorMessage,
    copied,
    elapsedSeconds,
    handleGenerate,
    handleCopy,
    handleDownload,
    reset,
  };
}

export type CoverLetterState = ReturnType<typeof useCoverLetter>;
