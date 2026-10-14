import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';

/**
 * useProfile — T1 of the UX refactor (specs S1, S6).
 *
 * Owns every *input-side* field of the tool: the uploaded PDF, the job
 * description / custom-requirements textarea, the contact URLs, the active
 * domain profile and all the option flags that end up in the `/api/generate`
 * FormData. There is no HTTP traffic in this hook — it is pure state plus the
 * localStorage persistence that was previously inline in `ToolApp.tsx`.
 */

// === Multi-domain tailoring (feat/multi-domain-tailoring) ===
// The selected profile dictates the prompt body that the backend composes:
//   'tech'          -> software engineers, full-stack, data/ML, DevOps, QA.
//   'hr_recruiting' -> talent acquisition analysts / recruiters / HRBPs.
//   'psychology'    -> psychologists (organizational / clinical / educational).
// Default is 'tech' to preserve the v2.5 UX byte-for-byte when the user does
// not pick anything.
export type DomainGame = 'tech' | 'hr_recruiting' | 'psychology';

/** Contact URLs are persisted under this key between visits (unchanged key). */
const CONTACT_STORAGE_KEY = 'jd-to-resume.contact';

export function useProfile() {
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [jd, setJd] = useState('');
  const [targetRole, setTargetRole] = useState('');
  const [githubUrl, setGithubUrl] = useState('');
  const [linkedinUrl, setLinkedinUrl] = useState('');
  const [portfolioUrl, setPortfolioUrl] = useState('');
  const [domainGame, setDomainGame] = useState<DomainGame>('tech');
  const [extractLinkedinInfo, setExtractLinkedinInfo] = useState(false);
  const [step2Mode, setStep2Mode] = useState<'jd' | 'custom'>('jd');
  const [customPrompt, setCustomPrompt] = useState<string>('');
  const [strictEditsOnly, setStrictEditsOnly] = useState<boolean>(false);
  const [selectedTheme, setSelectedTheme] = useState<string>('sb2nov');
  const [fitSinglePage, setFitSinglePage] = useState<boolean>(true);
  const [pageBreakSection, setPageBreakSection] = useState<string>('none');

  // ATS & AI Detection flags
  const [autoValidateATS, setAutoValidateATS] = useState(false);

  // === Edit-before-generate YAML editor (feat/yaml-editor) ===
  // When `editBeforeGenerate` is true, /api/generate streams the parsed
  // LLM JSON as YAML over SSE (the `yaml_ready` event) and stops without
  // rendering a PDF. The user edits the YAML in a textarea, then either
  // POSTs it to /api/render-from-yaml (T7) or /api/analyze-yaml (T7).
  const [editBeforeGenerate, setEditBeforeGenerate] = useState(false);

  // === Optional candidate photo ===
  // RenderCV embeds the photo from a filesystem path, so the File travels with
  // every generate / render-from-yaml request rather than being converted to a
  // data URI here. `photoPreview` is only the local <img> source.
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string>('');
  const photoInputRef = useRef<HTMLInputElement>(null);

  const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
  const PHOTO_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];

  const handlePhotoChange = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0];
    if (!picked) return;
    setPhotoError('');
    if (!PHOTO_TYPES.includes(picked.type)) {
      setPhotoError('Usá una imagen PNG, JPG, GIF o WebP.');
      return;
    }
    if (picked.size > MAX_PHOTO_BYTES) {
      setPhotoError('La foto supera el límite de 5 MB.');
      return;
    }
    // Revoke the previous object URL so repeated picks do not leak memory.
    if (photoPreview) URL.revokeObjectURL(photoPreview);
    setPhoto(picked);
    setPhotoPreview(URL.createObjectURL(picked));
  };

  const clearPhoto = () => {
    if (photoPreview) URL.revokeObjectURL(photoPreview);
    setPhoto(null);
    setPhotoPreview(null);
    setPhotoError('');
    if (photoInputRef.current) photoInputRef.current.value = '';
  };

  // Release the object URL when the hook unmounts.
  useEffect(() => {
    return () => {
      if (photoPreview) URL.revokeObjectURL(photoPreview);
    };
  }, [photoPreview]);

  // Persist contact URLs to localStorage so the user does not have to retype
  // them every time they open the app. Loaded on mount, written on change,
  // cleared by the explicit Reset button.
  useEffect(() => {
    try {
      const saved = localStorage.getItem(CONTACT_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (typeof parsed.githubUrl === 'string') setGithubUrl(parsed.githubUrl);
        if (typeof parsed.linkedinUrl === 'string') setLinkedinUrl(parsed.linkedinUrl);
        if (typeof parsed.portfolioUrl === 'string') setPortfolioUrl(parsed.portfolioUrl);
      }
    } catch {
      // Ignore corrupt localStorage entries silently.
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(CONTACT_STORAGE_KEY, JSON.stringify({ githubUrl, linkedinUrl, portfolioUrl }));
    } catch {
      // localStorage may be disabled (private mode, quota); persistence is best-effort.
    }
  }, [githubUrl, linkedinUrl, portfolioUrl]);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  /**
   * Resets only the fields the pre-refactor `handleResetProcess` used to clear
   * (file, JD, target role, contact URLs, domain, custom prompt and the
   * YAML-mode flag). The layout/theme flags intentionally survive the reset,
   * exactly as before.
   */
  const resetProfile = () => {
    setFile(null);
    setJd('');
    setTargetRole('');
    setGithubUrl('');
    setLinkedinUrl('');
    setPortfolioUrl('');
    setDomainGame('tech');
    setCustomPrompt('');
    setEditBeforeGenerate(false);
    clearPhoto();
    try {
      localStorage.removeItem(CONTACT_STORAGE_KEY);
    } catch {
      // best-effort
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return {
    file,
    setFile,
    fileInputRef,
    photo,
    photoPreview,
    photoError,
    photoInputRef,
    handlePhotoChange,
    clearPhoto,
    handleFileChange,
    jd,
    setJd,
    targetRole,
    setTargetRole,
    githubUrl,
    setGithubUrl,
    linkedinUrl,
    setLinkedinUrl,
    portfolioUrl,
    setPortfolioUrl,
    domainGame,
    setDomainGame,
    extractLinkedinInfo,
    setExtractLinkedinInfo,
    step2Mode,
    setStep2Mode,
    customPrompt,
    setCustomPrompt,
    strictEditsOnly,
    setStrictEditsOnly,
    selectedTheme,
    setSelectedTheme,
    fitSinglePage,
    setFitSinglePage,
    pageBreakSection,
    setPageBreakSection,
    autoValidateATS,
    setAutoValidateATS,
    editBeforeGenerate,
    setEditBeforeGenerate,
    resetProfile,
  };
}

export type Profile = ReturnType<typeof useProfile>;