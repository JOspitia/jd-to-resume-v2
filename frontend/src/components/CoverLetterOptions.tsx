import {
  Building2,
  MessageSquareQuote,
  Ruler,
  Languages,
  LayoutTemplate,
  Droplet,
  Link2,
} from 'lucide-react';

import { useDesignOptions } from '../lib/designOptions';
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
 * nothing for a plain text letter, while the tone, the length, the
 * company name, the language and the **PDF design** are exactly what the
 * letter needs.
 *
 * The design picker reuses the CV's own catalogue (the backend is the
 * source of truth for both the swatch hex and the layout ids), so the
 * letter matches the CV the user already picked.
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
  letterStyle: string;
  onLetterStyleChange: (value: string) => void;
  letterAccent: string;
  onLetterAccentChange: (value: string) => void;
  /** The LinkedIn the user typed in the form (section 3), for the hint. */
  linkedinUrl?: string;
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
  letterStyle,
  onLetterStyleChange,
  letterAccent,
  onLetterAccentChange,
  linkedinUrl,
}: CoverLetterOptionsProps) {
  const { letterStyles, palettes } = useDesignOptions();

  return (
    <div className="space-y-5">
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

      {/* PDF design — the same three looks the CV offers. */}
      <fieldset>
        <legend className={labelClass}>
          <LayoutTemplate className="w-3.5 h-3.5" /> Diseño del PDF
        </legend>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {letterStyles.map((style) => {
            const selected = letterStyle === style.id;
            return (
              <button
                key={style.id}
                type="button"
                onClick={() => onLetterStyleChange(style.id)}
                aria-pressed={selected}
                className={`p-2.5 text-left border-2 transition-all ${
                  selected
                    ? 'border-primary bg-primary/15 font-bold shadow-neo-sm text-foreground'
                    : 'border-border bg-card hover:bg-accent text-foreground'
                }`}
              >
                <span className="text-[10px] font-mono px-1 py-0.5 bg-muted text-foreground font-bold uppercase inline-block mb-1">
                  {style.badge}
                </span>
                <div className="text-xs font-serif font-bold text-foreground">{style.name}</div>
                <div className="text-[10px] text-muted-foreground mt-0.5 leading-tight">
                  {style.description}
                </div>
              </button>
            );
          })}
        </div>
      </fieldset>

      {/* Accent colour — the same palettes as the CV, the same safety
          rules: only the name, the rules and the links get tinted. */}
      <fieldset>
        <legend className={labelClass}>
          <Droplet className="w-3.5 h-3.5" /> Color de acento
        </legend>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {palettes.map((p) => {
            const selected = letterAccent === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onLetterAccentChange(p.id)}
                aria-pressed={selected}
                aria-label={`Color de acento: ${p.label}`}
                className={`p-2.5 text-left border-2 transition-all ${
                  selected
                    ? 'border-primary bg-primary/15 font-bold shadow-neo-sm text-foreground'
                    : 'border-border bg-card hover:bg-accent text-foreground'
                }`}
              >
                <span
                  aria-hidden="true"
                  className="block w-full h-6 border-2 border-border mb-1.5"
                  style={{ backgroundColor: p.hex }}
                />
                <div className="text-xs font-serif font-bold text-foreground">{p.label}</div>
              </button>
            );
          })}
        </div>
      </fieldset>

      <p className="text-xs text-muted-foreground flex items-start gap-1.5">
        <Link2 className="w-3.5 h-3.5 mt-0.5 shrink-0" />
        <span>
          El LinkedIn va en el encabezado y en la firma de la carta. Sale de tu CV si
          lo tiene; si no, agregalo en <strong>LINKS (opcional)</strong>, arriba, en
          la sección LA VACANTE.
          {linkedinUrl ? (
            <>
              {' '}
              <span className="font-mono break-all">({linkedinUrl})</span>
            </>
          ) : null}
        </span>
      </p>
    </div>
  );
}

export default CoverLetterOptions;
