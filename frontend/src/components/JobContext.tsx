import { Briefcase } from 'lucide-react';

/**
 * JobContext — T5 of the UX refactor (specs S5, S6).
 *
 * Step 3 of the main flow:
 *   1. Target role (compact single-line input, sits ABOVE the JD).
 *   2. Job description / requirements (full-width textarea).
 *   3. Profile links (GitHub | LinkedIn | Portfolio) in a single row
 *      so the user doesn't see 3 stacked input fields that eat vertical
 *      space.
 *
 * The step2Mode toggle (JD vs custom requirements) stays because it
 * changes the placeholder + label, not the layout.
 *
 * Wrapped by <Section number={3} title="LA VACANTE"> in ToolApp.
 */

export type JobContextProps = {
  jd: string;
  onJdChange: (value: string) => void;
  step2Mode: 'jd' | 'custom';
  onStep2ModeChange: (mode: 'jd' | 'custom') => void;
  targetRole: string;
  onTargetRoleChange: (value: string) => void;
  linkedinUrl: string;
  onLinkedinUrlChange: (value: string) => void;
  githubUrl: string;
  onGithubUrlChange: (value: string) => void;
  portfolioUrl: string;
  onPortfolioUrlChange: (value: string) => void;
};

const inputClass =
  "w-full border-2 border-border bg-card text-foreground p-2.5 font-sans text-sm focus:outline-none focus:ring-4 focus:ring-primary/20 placeholder:text-muted-foreground";

const linkInputClass = inputClass + ' placeholder:text-muted-foreground';

export function JobContext({
  jd,
  onJdChange,
  step2Mode,
  onStep2ModeChange,
  targetRole,
  onTargetRoleChange,
  linkedinUrl,
  onLinkedinUrlChange,
  githubUrl,
  onGithubUrlChange,
  portfolioUrl,
  onPortfolioUrlChange,
}: JobContextProps) {
  return (
    <div className="space-y-4">
      {/* Target role — compact single-line input, ABOVE the JD */}
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="target-role"
          className="font-bold font-mono text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1.5"
        >
          <Briefcase className="w-3.5 h-3.5" /> Cargo objetivo
        </label>
        <input
          id="target-role"
          type="text"
          value={targetRole}
          onChange={(e) => onTargetRoleChange(e.target.value)}
          placeholder="e.g. Senior Frontend Engineer"
          className={inputClass}
        />
      </div>

      {/* JD / requirements — full-width textarea with mode toggle */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <label
            htmlFor="jd"
            className="font-bold font-mono text-xs uppercase tracking-wide text-muted-foreground"
          >
            {step2Mode === 'jd' ? 'Oferta de trabajo' : 'Requerimientos de modificación'}
          </label>
          <div
            className="flex gap-1 bg-muted p-0.5 border border-border"
            role="tablist"
          >
            <button
              type="button"
              role="tab"
              aria-selected={step2Mode === 'jd'}
              onClick={() => onStep2ModeChange('jd')}
              className={`px-2.5 py-0.5 text-xs font-bold transition-all ${
                step2Mode === 'jd' ? 'bg-foreground text-background' : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              💼 Oferta
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={step2Mode === 'custom'}
              onClick={() => onStep2ModeChange('custom')}
              className={`px-2.5 py-0.5 text-xs font-bold transition-all ${
                step2Mode === 'custom' ? 'bg-foreground text-background' : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              📝 Requerimientos
            </button>
          </div>
        </div>
        <textarea
          id="jd"
          value={jd}
          onChange={(e) => onJdChange(e.target.value)}
          placeholder={
            step2Mode === 'jd'
              ? "Pega acá los requisitos o descripción de la oferta laboral..."
              : "Ejemplo: Cambiar fecha 2026-08 por 2026-09..."
          }
          className="w-full border-2 border-border bg-card text-foreground p-3 font-sans resize-y focus:outline-none focus:ring-4 focus:ring-primary/20 min-h-[160px] text-sm placeholder:text-muted-foreground"
        />
        <p className="text-xs text-muted-foreground italic">
          * Si no contás con una oferta específica, cambiá a "Requerimientos" o dejá vacío para optimización general ATS.
        </p>
      </div>

      {/* Profile links — single row */}
      <div className="border-t-2 border-border pt-3">
        <div className="text-xs font-mono text-muted-foreground uppercase tracking-wide mb-2">
          Links (opcional)
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <input
            type="url"
            value={githubUrl}
            onChange={(e) => onGithubUrlChange(e.target.value)}
            placeholder="GitHub URL"
            aria-label="GitHub URL"
            className={linkInputClass}
          />
          <input
            type="url"
            value={linkedinUrl}
            onChange={(e) => onLinkedinUrlChange(e.target.value)}
            placeholder="LinkedIn URL"
            aria-label="LinkedIn URL"
            className={linkInputClass}
          />
          <input
            type="url"
            value={portfolioUrl}
            onChange={(e) => onPortfolioUrlChange(e.target.value)}
            placeholder="Portafolio / Web"
            aria-label="Portafolio / Web"
            className={linkInputClass}
          />
        </div>
      </div>
    </div>
  );
}

export default JobContext;
