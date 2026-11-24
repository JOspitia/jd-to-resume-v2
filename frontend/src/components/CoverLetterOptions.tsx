import { Building2, MessageSquareQuote, Ruler, Languages } from 'lucide-react';

import {
  TONE_LABELS,
  LENGTH_LABELS,
  LANGUAGE_LABELS,
  type CoverLetterTone,
  type CoverLetterLength,
  type CoverLetterLanguage,
} from '../types/coverLetter';

/**
 * CoverLetterOptions — the letter-specific controls.
 *
 * These replace the CV's "OPCIONES AVANZADAS" section when the user
 * picks the cover-letter deliverable: a theme or an accent colour mean
 * nothing for a text letter, while the tone, the length, the company name
 * and the language are exactly what the letter prompt needs.
 *
 * Company name matters: when it is known, the letter addresses the
 * company by name and argues the match against that company; when it is
 * blank, the letter falls back to a neutral "Estimado equipo de
 * Selección:" and never invents a name.
 */

export type CoverLetterOptionsProps = {
  companyName: string;
  onCompanyNameChange: (value: string) => void;
  tone: CoverLetterTone;
  onToneChange: (value: CoverLetterTone) => void;
  length: CoverLetterLength;
  onLengthChange: (value: CoverLetterLength) => void;
  language: CoverLetterLanguage;
  onLanguageChange: (value: CoverLetterLanguage) => void;
};

const inputClass =
  'w-full border-2 border-border bg-card text-foreground p-2.5 font-sans text-sm focus:outline-none focus:ring-4 focus:ring-primary/20 placeholder:text-muted-foreground';

const selectClass = `${inputClass} appearance-none cursor-pointer`;

const labelClass =
  'font-bold font-mono text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1.5';

export function CoverLetterOptions({
  companyName,
  onCompanyNameChange,
  tone,
  onToneChange,
  length,
  onLengthChange,
  language,
  onLanguageChange,
}: CoverLetterOptionsProps) {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="cover-company" className={labelClass}>
          <Building2 className="w-3.5 h-3.5" /> Empresa (opcional)
        </label>
        <input
          id="cover-company"
          type="text"
          value={companyName}
          onChange={(e) => onCompanyNameChange(e.target.value)}
          placeholder="e.g. Tiendas Falabella"
          className={inputClass}
        />
        <p className="text-xs text-muted-foreground italic">
          * Si lo dejás vacío, la carta salutará al equipo de selección sin inventar nombres.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="cover-tone" className={labelClass}>
            <MessageSquareQuote className="w-3.5 h-3.5" /> Tono
          </label>
          <select
            id="cover-tone"
            value={tone}
            onChange={(e) => onToneChange(e.target.value as CoverLetterTone)}
            className={selectClass}
          >
            {(Object.keys(TONE_LABELS) as CoverLetterTone[]).map((key) => (
              <option key={key} value={key}>
                {TONE_LABELS[key]}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cover-length" className={labelClass}>
            <Ruler className="w-3.5 h-3.5" /> Longitud
          </label>
          <select
            id="cover-length"
            value={length}
            onChange={(e) => onLengthChange(e.target.value as CoverLetterLength)}
            className={selectClass}
          >
            {(Object.keys(LENGTH_LABELS) as CoverLetterLength[]).map((key) => (
              <option key={key} value={key}>
                {LENGTH_LABELS[key]}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cover-language" className={labelClass}>
            <Languages className="w-3.5 h-3.5" /> Idioma
          </label>
          <select
            id="cover-language"
            value={language}
            onChange={(e) => onLanguageChange(e.target.value as CoverLetterLanguage)}
            className={selectClass}
          >
            {(Object.keys(LANGUAGE_LABELS) as CoverLetterLanguage[]).map((key) => (
              <option key={key} value={key}>
                {LANGUAGE_LABELS[key]}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

export default CoverLetterOptions;
