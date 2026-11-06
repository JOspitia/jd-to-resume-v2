import { motion } from 'framer-motion';
import { Palette, LayoutTemplate, Droplet, Check, X } from 'lucide-react';
import { useDesignOptions } from '../lib/designOptions';
import { Button } from './ui/Button';

/**
 * RedesignPanel — change the look of the CV without touching the text.
 *
 * Shown inside the results card once a PDF exists. The user picks another
 * template and/or accent colour and the panel re-renders the *same* YAML
 * that produced the current PDF, so the wording stays exactly as it is.
 *
 * This is deliberately a separate surface from the "Opciones avanzadas"
 * picker: that one configures the *next* generation (which does run the
 * LLM), while this one re-renders the document the user is already looking
 * at (which does not).
 */

export type RedesignPanelProps = {
  theme: string;
  accent: string;
  onThemeChange: (theme: string) => void;
  onAccentChange: (accent: string) => void;
  onApply: () => void;
  onCancel: () => void;
  applying: boolean;
  errorMessage: string;
};

export function RedesignPanel({
  theme,
  accent,
  onThemeChange,
  onAccentChange,
  onApply,
  onCancel,
  applying,
  errorMessage,
}: RedesignPanelProps) {
  const { themes, palettes } = useDesignOptions();

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-card border-2 border-border p-4 space-y-4"
      role="group"
      aria-label="Cambiar el diseño del CV sin modificar el texto"
    >
      <div className="flex items-start gap-2">
        <Palette className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div>
          <div className="font-bold font-mono text-xs uppercase tracking-wide text-foreground">
            Cambiar solo el diseño
          </div>
          <p className="text-xs text-muted-foreground mt-1 leading-tight">
            Se vuelve a renderizar <strong>el mismo CV</strong> con otra plantilla o
            color. <strong>El texto no se toca</strong> y no se llama a la IA.
          </p>
        </div>
      </div>

      {/* Templates */}
      <fieldset>
        <legend className="font-bold font-mono text-[10px] uppercase tracking-wide text-muted-foreground flex items-center gap-1.5 mb-2">
          <LayoutTemplate className="w-3 h-3" aria-hidden="true" /> Plantilla
        </legend>
        <div className="grid grid-cols-2 gap-2" role="group" aria-label="Plantilla del CV">
          {themes.map((t) => {
            const selected = theme === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => onThemeChange(t.id)}
                aria-pressed={selected}
                aria-label={`Plantilla: ${t.name}`}
                className={`p-2 text-left border-2 transition-all ${
                  selected
                    ? 'border-primary bg-primary/15 shadow-neo-sm'
                    : 'border-border bg-card hover:bg-accent'
                }`}
              >
                <div className="flex items-center gap-1.5">
                  {selected && <Check className="w-3 h-3 shrink-0 text-primary" aria-hidden="true" />}
                  <span className="text-xs font-serif font-bold text-foreground">{t.name}</span>
                </div>
                <div className="text-[10px] text-muted-foreground mt-0.5 leading-tight">
                  {t.description}
                </div>
              </button>
            );
          })}
        </div>
      </fieldset>

      {/* Accent colours */}
      <fieldset>
        <legend className="font-bold font-mono text-[10px] uppercase tracking-wide text-muted-foreground flex items-center gap-1.5 mb-2">
          <Droplet className="w-3 h-3" aria-hidden="true" /> Color de acento
        </legend>
        <div className="grid grid-cols-4 gap-2" role="group" aria-label="Color de acento del CV">
          {palettes.map((p) => {
            const selected = accent === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onAccentChange(p.id)}
                aria-pressed={selected}
                aria-label={`Color de acento: ${p.label}`}
                title={p.label}
                className={`p-1.5 border-2 transition-all ${
                  selected
                    ? 'border-primary bg-primary/15 shadow-neo-sm'
                    : 'border-border bg-card hover:bg-accent'
                }`}
              >
                <span
                  aria-hidden="true"
                  className="block w-full h-5 border-2 border-border"
                  style={{ backgroundColor: p.hex }}
                />
                <span className="block text-[9px] font-serif font-bold text-foreground mt-1 truncate">
                  {p.label}
                </span>
              </button>
            );
          })}
        </div>
      </fieldset>

      {errorMessage && (
        <p role="alert" className="text-xs text-destructive border-2 border-destructive p-2 leading-tight">
          {errorMessage}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Button
          onClick={onApply}
          disabled={applying}
          variant="primary"
          size="md"
          aria-label="Aplicar el nuevo diseño al CV actual sin cambiar el texto"
        >
          <Palette className="w-4 h-4" aria-hidden="true" />
          {applying ? 'Aplicando…' : 'Aplicar diseño'}
        </Button>
        <Button onClick={onCancel} disabled={applying} variant="outline" size="md">
          <X className="w-4 h-4" aria-hidden="true" />
          Cancelar
        </Button>
      </div>
    </motion.div>
  );
}

export default RedesignPanel;
