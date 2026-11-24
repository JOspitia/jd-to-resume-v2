import { useEffect, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';

import { readSession, writeSession } from '../lib/session';

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
//   'general'       -> customer service, commercial, retail and operations
//                      roles (sales, cash handling, merchandising, restocking).
// Default is 'tech' to preserve the v2.5 UX byte-for-byte when the user does
// not pick anything.
export type DomainGame = 'tech' | 'hr_recruiting' | 'psychology' | 'general';

/**
 * What the tool produces. The two deliverables share the first three
 * steps (perfil, tu CV, la vacante) and diverge afterwards: the CV
 * renders a PDF, the cover letter returns a narrative to copy.
 */
export type Deliverable = 'cv' | 'cover_letter';

/** Register of the cover letter. */
export type CoverLetterTone = 'professional' | 'persuasive' | 'warm' | 'concise';

/** Word budget of the cover letter. */
export type CoverLetterLength = 'short' | 'medium' | 'long';

/** Language of the cover letter: follow the job description, or force one. */
export type CoverLetterLanguage = 'auto' | 'es' | 'en';

/** Contact URLs are persisted under this key between visits (unchanged key). */
const CONTACT_STORAGE_KEY = 'jd-to-resume.contact';

/**
 * The form state (everything except the uploaded files) is persisted in
 * sessionStorage under this key.
 *
 * The reason is the "Preview"/"Download" bug: those links used to
 * navigate the browser to the PDF, and in the embedded browser that
 * replaces the SPA. Coming back reloaded the app from scratch, so every
 * field the user had typed was gone. Persisting the form means a reload
 * puts the user back exactly where they were.
 *
 * sessionStorage (not localStorage) because this is *work in progress*,
 * not a durable preference: it must not leak into a visit that starts
 * days later.
 */
const PROFILE_SESSION_KEY = 'profile';

/** The subset of the form that survives a reload. */
type ProfileSnapshot = {
  jd: string;
  targetRole: string;
  domainGame: DomainGame;
  extractLinkedinInfo: boolean;
  step2Mode: 'jd' | 'custom';
  customPrompt: string;
  strictEditsOnly: boolean;
  translateOnly: boolean;
  selectedTheme: string;
  accentColor: string;
  fitSinglePage: boolean;
  pageBreakSection: string;
  deliverable: Deliverable;
  companyName: string;
  coverLetterTone: CoverLetterTone;
  coverLetterLength: CoverLetterLength;
  coverLetterLanguage: CoverLetterLanguage;
  letterStyle: string;
  letterAccent: string;
  autoValidateATS: boolean;
  editBeforeGenerate: boolean;
};

/** Reads a string field from a persisted snapshot, falling back to the default. */
function savedString(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback;
}

/** Reads a boolean field from a persisted snapshot, falling back to the default. */
function savedBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

export function useProfile() {
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /**
   * The form is restored from sessionStorage on mount (PROFILE_SESSION_KEY).
   *
   * The snapshot is read ONCE and used as the initial value of every field,
   * instead of restoring it in an effect: the first render already shows the
   * saved form, so there is no flash of empty inputs and no
   * setState-inside-an-effect (which React flags as a cascading render).
   */
  const [saved] = useState<Partial<ProfileSnapshot> | null>(() =>
    readSession<Partial<ProfileSnapshot>>(PROFILE_SESSION_KEY),
  );

  const [jd, setJd] = useState(() => savedString(saved?.jd, ''));
  const [targetRole, setTargetRole] = useState(() => savedString(saved?.targetRole, ''));
  const [githubUrl, setGithubUrl] = useState('');
  const [linkedinUrl, setLinkedinUrl] = useState('');
  const [portfolioUrl, setPortfolioUrl] = useState('');
  const [domainGame, setDomainGame] = useState<DomainGame>(
    () => (saved?.domainGame as DomainGame | undefined) ?? 'tech',
  );
  const [extractLinkedinInfo, setExtractLinkedinInfo] = useState(() =>
    savedBoolean(saved?.extractLinkedinInfo, false),
  );
  const [step2Mode, setStep2Mode] = useState<'jd' | 'custom'>(() =>
    saved?.step2Mode === 'custom' ? 'custom' : 'jd',
  );
  const [customPrompt, setCustomPrompt] = useState<string>(() =>
    savedString(saved?.customPrompt, ''),
  );
  const [strictEditsOnly, setStrictEditsOnly] = useState<boolean>(() =>
    savedBoolean(saved?.strictEditsOnly, false),
  );
  /**
   * Faithful translation mode: translate the uploaded CV to English without
   * tailoring it to any job description. It changes what the pipeline does
   * (a different prompt, no JD, no LinkedIn enrichment), so it is a mode
   * and not a micro-option.
   */
  const [translateOnly, setTranslateOnly] = useState<boolean>(() =>
    savedBoolean(saved?.translateOnly, false),
  );
  const [selectedTheme, setSelectedTheme] = useState<string>(() =>
    savedString(saved?.selectedTheme, 'sb2nov'),
  );
  // === Accent colour for the rendered CV ===
  // An id from the backend catalogue (`/api/design-options`): "none" keeps
  // the black & white output, the others tint the name, the section titles
  // and the links. The colour never changes the layout, so the ATS parse
  // is identical whichever value is picked.
  const [accentColor, setAccentColor] = useState<string>(() =>
    savedString(saved?.accentColor, 'none'),
  );
  const [fitSinglePage, setFitSinglePage] = useState<boolean>(() =>
    savedBoolean(saved?.fitSinglePage, true),
  );
  const [pageBreakSection, setPageBreakSection] = useState<string>(() =>
    savedString(saved?.pageBreakSection, 'none'),
  );

  // === Cover letter deliverable ===
  // `deliverable` picks what the primary CTA produces. The letter-specific
  // controls only make sense in the cover-letter mode, so they live here
  // next to the rest of the form state.
  const [deliverable, setDeliverable] = useState<Deliverable>(() =>
    saved?.deliverable === 'cover_letter' ? 'cover_letter' : 'cv',
  );
  const [companyName, setCompanyName] = useState<string>(() =>
    savedString(saved?.companyName, ''),
  );
  const [coverLetterTone, setCoverLetterTone] = useState<CoverLetterTone>(() =>
    (saved?.coverLetterTone as CoverLetterTone | undefined) ?? 'professional',
  );
  const [coverLetterLength, setCoverLetterLength] = useState<CoverLetterLength>(() =>
    (saved?.coverLetterLength as CoverLetterLength | undefined) ?? 'medium',
  );
  const [coverLetterLanguage, setCoverLetterLanguage] = useState<CoverLetterLanguage>(() =>
    (saved?.coverLetterLanguage as CoverLetterLanguage | undefined) ?? 'auto',
  );
  /** Letter layout for the PDF: mirrors the CV designs (classic / modern / sidebar). */
  const [letterStyle, setLetterStyle] = useState<string>(() =>
    savedString(saved?.letterStyle, 'classic'),
  );
  /** Accent palette id for the letter PDF (same catalogue as the CV). */
  const [letterAccent, setLetterAccent] = useState<string>(() =>
    savedString(saved?.letterAccent, 'none'),
  );

  // ATS & AI Detection flags
  const [autoValidateATS, setAutoValidateATS] = useState(() =>
    savedBoolean(saved?.autoValidateATS, false),
  );

  // === Edit-before-generate YAML editor (feat/yaml-editor) ===
  // When `editBeforeGenerate` is true, /api/generate streams the parsed
  // LLM JSON as YAML over SSE (the `yaml_ready` event) and stops without
  // rendering a PDF. The user edits the YAML in a textarea, then either
  // POSTs it to /api/render-from-yaml (T7) or /api/analyze-yaml (T7).
  const [editBeforeGenerate, setEditBeforeGenerate] = useState(() =>
    savedBoolean(saved?.editBeforeGenerate, false),
  );

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
    // The previous object URL is revoked by the effect cleanup below
    // whenever ``photoPreview`` changes — no manual revoke needed here,
    // which used to double-revoke the same URL.
    setPhoto(picked);
    setPhotoPreview(URL.createObjectURL(picked));
  };

  const clearPhoto = () => {
    // Effect cleanup revokes the active URL when ``photoPreview`` flips
    // back to null; no manual revoke needed here either.
    setPhoto(null);
    setPhotoPreview(null);
    setPhotoError('');
    if (photoInputRef.current) photoInputRef.current.value = '';
  };

  // Release the active object URL whenever the user picks a different
  // photo, clears it, or unmounts. Single source of truth — the manual
  // revokes that used to live in handlePhotoChange / clearPhoto would
  // double-revoke the same URL on every photo swap.
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

  // === Session persistence (reload-safe form state) ===
  //
  // The restore happens at mount (lazy initial state, see `saved`); this
  // effect keeps the snapshot in sync with the form. It also covers the
  // contact URLs, which are a durable preference and live in
  // localStorage instead.
  useEffect(() => {
    const snapshot: ProfileSnapshot = {
      jd,
      targetRole,
      domainGame,
      extractLinkedinInfo,
      step2Mode,
      customPrompt,
      strictEditsOnly,
      translateOnly,
      selectedTheme,
      accentColor,
      fitSinglePage,
      pageBreakSection,
      deliverable,
      companyName,
      coverLetterTone,
      coverLetterLength,
      coverLetterLanguage,
      letterStyle,
      letterAccent,
      autoValidateATS,
      editBeforeGenerate,
    };
    writeSession(PROFILE_SESSION_KEY, snapshot);
  }, [
    jd,
    targetRole,
    domainGame,
    extractLinkedinInfo,
    step2Mode,
    customPrompt,
    strictEditsOnly,
    translateOnly,
    selectedTheme,
    accentColor,
    fitSinglePage,
    pageBreakSection,
    deliverable,
    companyName,
    coverLetterTone,
    coverLetterLength,
    coverLetterLanguage,
    letterStyle,
    letterAccent,
    autoValidateATS,
    editBeforeGenerate,
  ]);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  /**
   * Resets the input fields for a new "CV run".
   *
   * **What this clears (per-process-input state):**
   *   * uploaded PDF + candidate photo (both FormData artifacts)
   *   * job-description / custom-requirements text, target role
   *   * contact URLs (also dropped from localStorage)
   *   * domain game, custom prompt, edit-before-generate flag
   *
   * **What this intentionally preserves (session-level preferences):**
   *   * ``selectedTheme``     — the picked RenderCV theme is a visual
   *                             preference, not per-CV.
   *   * ``accentColor``       — the picked accent colour, same reason.
   *   * ``fitSinglePage``     — layout choice, not per-CV.
   *   * ``pageBreakSection`` — ditto.
   *
   * **Behaviour-deprecated flags that ALSO survive reset, with rationale:**
   *   * ``strictEditsOnly``        — surgical-edit mode. Choosing to
   *                                  "rebuild every section" by default would
   *                                  be surprising; we trust the user to
   *                                  toggle it back when they want it. Same
   *                                  semantic as the pre-refactor reset.
   *   * ``extractLinkedinInfo``    — opt-in enrichment that re-reads the
   *                                  LinkedIn profile on each run; default-off
   *                                  matches the v2.5 reset behaviour.
   *   * ``step2Mode``              — UI tab toggle ('jd' | 'custom'); not
   *                                  a process state, just which textarea is
   *                                  visible.
   *
   * Documented here because the asymmetry (some prefs survive, others
   * don't) has historically confused reviewers expecting a wholesale
   * reset.
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
    setDeliverable('cv');
    setCompanyName('');
    setCoverLetterTone('professional');
    setCoverLetterLength('medium');
    setCoverLetterLanguage('auto');
    setLetterStyle('classic');
    setLetterAccent('none');
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
    translateOnly,
    setTranslateOnly,
    selectedTheme,
    setSelectedTheme,
    accentColor,
    setAccentColor,
    fitSinglePage,
    setFitSinglePage,
    pageBreakSection,
    setPageBreakSection,
    autoValidateATS,
    setAutoValidateATS,
    editBeforeGenerate,
    setEditBeforeGenerate,
    deliverable,
    setDeliverable,
    companyName,
    setCompanyName,
    coverLetterTone,
    setCoverLetterTone,
    coverLetterLength,
    setCoverLetterLength,
    coverLetterLanguage,
    setCoverLetterLanguage,
    letterStyle,
    setLetterStyle,
    letterAccent,
    setLetterAccent,
    resetProfile,
  };
}

export type Profile = ReturnType<typeof useProfile>;