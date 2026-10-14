import { motion } from 'framer-motion';
import { Play, Clock, ShieldCheck, RotateCcw, Languages } from 'lucide-react';

/**
 * ActionBar — T9 of the UX refactor (spec S3).
 *
 * Fixed bottom bar: the primary "generate" action plus the contextual actions
 * (standalone ATS audit, translate to English, start over) stay reachable no
 * matter how far the user has scrolled down the form.
 */

export type ActionBarProps = {
  status: 'idle' | 'generating' | 'success' | 'error';
  atsStatus: 'idle' | 'analyzing' | 'success' | 'error';
  elapsedSeconds: number;
  hasFile: boolean;
  lastOutputLanguage: 'en' | 'es' | 'unknown';
  showReset: boolean;
  onGenerate: (customInstructionsOverride?: string, baseResumeFilename?: string, forceTranslate?: boolean) => void;
  onAudit: () => void;
  onReset: () => void;
};

export function ActionBar({
  status,
  atsStatus,
  elapsedSeconds,
  hasFile,
  lastOutputLanguage,
  showReset,
  onGenerate,
  onAudit,
  onReset,
}: ActionBarProps) {
  const generating = status === 'generating';
  const analyzing = atsStatus === 'analyzing';

  return (
    <div className="fixed bottom-0 inset-x-0 z-40 px-4 pb-4 pointer-events-none">
      <div className="max-w-5xl mx-auto pointer-events-auto">
        <div className="rm-box bg-white px-4 py-3 md:px-6 md:py-4 flex flex-col md:flex-row items-stretch md:items-center justify-center gap-3 md:gap-4">
          {/* Primary action */}
          <button
            onClick={() => onGenerate()}
            disabled={generating}
            className="rm-btn bg-blue-700 hover:bg-blue-800 text-white disabled:opacity-70 disabled:cursor-not-allowed px-10 py-4 md:py-5 text-lg md:text-xl flex items-center justify-center gap-3"
          >
            {generating ? (
              <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}>
                <Clock className="w-6 h-6" />
              </motion.div>
            ) : (
              <Play className="w-6 h-6 fill-current" />
            )}
            {generating ? `GENERANDO (${elapsedSeconds}s / 60s)...` : 'GENERATE TAILORED RESUME'}
          </button>

          {/* Standalone ATS-only audit button */}
          <button
            onClick={onAudit}
            disabled={analyzing || !hasFile}
            title={!hasFile ? 'Sube un PDF primero' : 'Auditar el CV actual sin generar uno nuevo'}
            className="rm-btn bg-yellow-400 hover:bg-yellow-500 text-black disabled:opacity-50 disabled:cursor-not-allowed px-6 md:px-8 py-4 md:py-5 text-base md:text-lg flex items-center justify-center gap-3"
          >
            {analyzing ? (
              <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }}>
                <Clock className="w-6 h-6" />
              </motion.div>
            ) : (
              <ShieldCheck className="w-6 h-6" />
            )}
            {analyzing ? `AUDITANDO (${elapsedSeconds}s / 60s)...` : '📊 SOLO AUDITAR ATS'}
          </button>

          {/* Translate to English — always visible. Enabled as soon as a PDF is loaded,
              so the user can translate the uploaded CV directly without first running the
              full tailoring pipeline. When no PDF is uploaded, the button is disabled. */}
          <button
            onClick={() => {
              if (!hasFile) return;
              onGenerate(undefined, undefined, true);
            }}
            disabled={!hasFile || lastOutputLanguage === 'en' || generating}
            title={
              !hasFile
                ? 'Upload a PDF resume first'
                : lastOutputLanguage === 'en'
                  ? 'CV already in English'
                  : 'This may take 30-90s'
            }
            className="rm-btn bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed px-6 py-4 md:py-5 text-base md:text-lg flex items-center justify-center gap-2 font-bold"
          >
            <Languages className="w-5 h-5" />
            Translate to English
          </button>

          {/* Clear / Reset Button */}
          {showReset && (
            <button
              onClick={onReset}
              disabled={generating || analyzing}
              title="Limpiar campos y borrar caché de CVs"
              className="rm-btn bg-white hover:bg-rose-50 border-2 border-black text-rose-700 px-6 py-4 md:py-5 text-base md:text-lg flex items-center justify-center gap-2 font-bold"
            >
              <RotateCcw className="w-5 h-5 text-rose-600" />
              LIMPIAR / NUEVO
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default ActionBar;