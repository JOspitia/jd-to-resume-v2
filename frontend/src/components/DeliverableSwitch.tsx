import { FileText, PenLine } from 'lucide-react';

import type { Deliverable } from '../types/coverLetter';

/**
 * DeliverableSwitch — the first control of the tool.
 *
 * The app produces two different documents from the same inputs:
 *   * "CV"            → the ATS-optimised PDF (the original flow).
 *   * "Carta"         → a cover letter (new deliverable).
 *
 * They share steps 1-3 (perfil, tu CV, la vacante) because both read the
 * same resume and the same job description; they differ in what happens
 * afterwards: the CV renders a PDF, the letter returns a narrative. The
 * switch is therefore placed BEFORE the shared steps so the user picks the
 * deliverable first and the rest of the form adapts (the advanced
 * options and the CTA change with it).
 */

export type DeliverableSwitchProps = {
  value: Deliverable;
  onChange: (value: Deliverable) => void;
};

const OPTIONS = [
  {
    id: 'cv' as const,
    Icon: FileText,
    label: 'CV adaptado',
    description: 'PDF optimizado para ATS, con el diseño que elijas.',
  },
  {
    id: 'cover_letter' as const,
    Icon: PenLine,
    label: 'Carta de presentación',
    description: 'Carta en texto para copiar y pegar en la postulación.',
  },
];

export function DeliverableSwitch({ value, onChange }: DeliverableSwitchProps) {
  return (
    <div
      className="grid sm:grid-cols-2 gap-4"
      role="radiogroup"
      aria-label="Qué querés generar"
    >
      {OPTIONS.map(({ id, Icon, label, description }) => {
        const selected = value === id;
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(id)}
            className={`text-left p-4 border-2 transition-all ${
              selected
                ? 'border-primary bg-primary/10 shadow-[4px_4px_0_0_hsl(var(--primary))]'
                : 'border-border bg-card hover:border-primary/50'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <span
                className={`flex items-center justify-center w-9 h-9 border-2 shrink-0 ${
                  selected
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-muted text-muted-foreground border-border'
                }`}
              >
                <Icon className="w-5 h-5" />
              </span>
              <span className="font-bold font-serif text-foreground text-sm">
                {label}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-2 leading-snug">
              {description}
            </p>
          </button>
        );
      })}
    </div>
  );
}

export default DeliverableSwitch;
