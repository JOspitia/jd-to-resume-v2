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
  /** Name + contact line, exactly as in the resume. */
  signature: string;
  /** The whole letter, assembled by the backend — ready to copy/paste. */
  plain_text: string;
  meta: CoverLetterMeta;
};

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
