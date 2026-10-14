import { motion } from 'framer-motion';

/**
 * JobContext — T7 of the UX refactor (specs S1, S6).
 *
 * Step 2 of the main flow: the job description (or free-form requirements)
 * textarea plus the "Additional Context" links that the backend injects into
 * the prompt (`jd`, `target_role`, `linkedin_url`, `github_url`,
 * `portfolio_url`).
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
  "w-full border-2 border-black bg-white p-3 font-sans focus:outline-none focus:ring-4 focus:ring-blue-100";

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
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay: 0.2 }}
      className="rm-box p-8 md:p-10 flex flex-col bg-white relative"
    >
      <div className="absolute -top-4 -left-4 rm-tag bg-orange-500 text-white px-4 py-2 text-lg">STEP_2</div>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 mt-2">
        <h2 className="text-xl font-bold font-serif">
          {step2Mode === 'jd' ? 'Oferta de Trabajo (Job Description)' : 'Requerimientos de Modificación'}
        </h2>
        <div className="flex gap-1 bg-gray-100 p-1 border-2 border-black">
          <button
            type="button"
            onClick={() => onStep2ModeChange('jd')}
            className={`px-3 py-1 text-xs font-bold transition-all ${step2Mode === 'jd' ? 'bg-black text-white' : 'text-gray-700 hover:bg-gray-200'}`}
          >
            💼 Oferta de Trabajo
          </button>
          <button
            type="button"
            onClick={() => onStep2ModeChange('custom')}
            className={`px-3 py-1 text-xs font-bold transition-all ${step2Mode === 'custom' ? 'bg-black text-white' : 'text-gray-700 hover:bg-gray-200'}`}
          >
            📝 Requerimientos CV
          </button>
        </div>
      </div>

      <textarea
        value={jd}
        onChange={(e) => onJdChange(e.target.value)}
        placeholder={
          step2Mode === 'jd'
            ? "Pega aquí los requisitos o descripción de la oferta laboral..."
            : "Ejemplo: Cambiar fecha 2026-08 por 2026-09..."
        }
        className="flex-1 w-full border-2 border-black bg-white p-5 font-sans resize-none focus:outline-none focus:ring-4 focus:ring-blue-100 min-h-[200px] text-base placeholder-gray-500"
      />

      <p className="mt-2 text-xs text-gray-500 italic">
        * Si no cuentas con una oferta específica, puedes alternar a "Requerimientos CV" o dejar este campo vacío para optimización general ATS.
      </p>

      {/* Additional Context — the URLs/role that enrich the prompt. */}
      <div className="mt-8 border-t-2 border-gray-300 pt-6 grid md:grid-cols-2 gap-6">
        <div className="flex flex-col gap-2">
          <label className="font-bold font-mono text-sm uppercase tracking-wide">Target Role Title</label>
          <input
            type="text"
            value={targetRole}
            onChange={(e) => onTargetRoleChange(e.target.value)}
            placeholder="e.g. Senior Frontend Eng"
            className={inputClass}
          />
        </div>

        <div className="flex flex-col gap-2">
          <label className="font-bold font-mono text-sm uppercase tracking-wide">LinkedIn Profile</label>
          <input
            type="url"
            value={linkedinUrl}
            onChange={(e) => onLinkedinUrlChange(e.target.value)}
            placeholder="https://linkedin.com/in/..."
            className={inputClass}
          />
        </div>

        <div className="flex flex-col gap-2">
          <label className="font-bold font-mono text-sm uppercase tracking-wide">Portafolio / Sitio Web</label>
          <input
            type="url"
            value={portfolioUrl}
            onChange={(e) => onPortfolioUrlChange(e.target.value)}
            placeholder="https://miportafolio.com"
            className={inputClass}
          />
        </div>

        <div className="flex flex-col gap-2">
          <label className="font-bold font-mono text-sm uppercase tracking-wide">GitHub(Opcional)</label>
          <input
            type="url"
            value={githubUrl}
            onChange={(e) => onGithubUrlChange(e.target.value)}
            placeholder="https://github.com/..."
            className={inputClass}
          />
        </div>
      </div>
    </motion.div>
  );
}

export default JobContext;