/**
 * Types for the cover-letter deliverable.
 *
 * The response contract mirrors `backend/application/services/cover_letter_service.py`:
 * the backend normalises the model's free-form answer into a structured
 * letter plus a ready-to-copy `plain_text`.
 */

/** What the user asked the tool to produce. */
export type Deliverable = 'cv' | 'cover_letter';

/** Register of the letter. */
export type CoverLetterTone = 'professional' | 'persuasive' | 'warm' | 'concise';

/** Word budget of the letter. */
export type CoverLetterLength = 'short' | 'medium' | 'long';

/** Language of the letter: follow the job description, or force one. */
export type CoverLetterLanguage = 'auto' | 'es' | 'en';

export type CoverLetterMeta = {
  word_count: number;
  language: string;
  domain_game: string;
  tone: string;
  length: string;
  letter_style: string;
  accent: string;
};

/**
 * The contact block of the letterhead. Every field is a fact: it comes
 * from the candidate's own PDF or from the links the user typed in the
 * form — never from the model.
 */
export type CoverLetterContact = {
  name: string;
  email: string;
  phone: string;
  linkedin: string;
  github: string;
  portfolio: string;
};

export type CoverLetter = {
  /** One line addressing the hiring team. */
  salutation: string;
  /** Two or three sentences: why this vacancy, why this candidate. */
  opening: string;
  /** The body paragraphs, one argument each. */
  body: string[];
  /** Availability, practical facts and the next step. */
  closing: string;
  /** Name + contact line + profile URLs, built from real data. */
  signature: string;
  /** The whole letter, assembled by the backend — ready to copy/paste. */
  plain_text: string;
  /** What the letterhead shows. */
  contact: CoverLetterContact;
  /** The rendered PDF, served by /api/download. */
  pdf_url?: string;
  pdf_filename?: string;
  meta: CoverLetterMeta;
};

/** The cover-letter layouts the backend can render. */
export type LetterStyle = 'classic' | 'modern' | 'sidebar';

/** Human-readable labels for the tone selector. */
export const TONE_LABELS: Record<CoverLetterTone, string> = {
  professional: 'Profesional',
  persuasive: 'Persuasiva',
  warm: 'Cercana',
  concise: 'Directa',
};

/** Human-readable labels for the length selector. */
export const LENGTH_LABELS: Record<CoverLetterLength, string> = {
  short: 'Corta (120-180 palabras)',
  medium: 'Media (220-320 palabras)',
  long: 'Larga (350-450 palabras)',
};

/** Human-readable labels for the language selector. */
export const LANGUAGE_LABELS: Record<CoverLetterLanguage, string> = {
  auto: 'Idioma de la oferta',
  es: 'Español',
  en: 'Inglés',
};
