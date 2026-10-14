import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle, Eye, Download, BarChart3, Languages, RotateCcw, Code2 } from 'lucide-react';
import { ScoreHistory } from './ScoreHistory';
import type { ScoreEntry } from '../hooks/useAudit';

/**
 * ResultsPanel — T11 of the UX refactor (spec S4, S6).
 *
 * Success card shown *below* the main flow once a PDF is ready: it never
 * replaces the form, so the user can keep tweaking the inputs and generate
 * again. The "Editar YAML directamente" CTA is the most prominent next step of
 * the iteration loop.
 */

type AuditScores = {
  ats_score?: number;
  ai_detection_score?: number;
  match_level?: string;
} | null;

export type ResultsPanelProps = {
  status: 'idle' | 'generating' | 'success' | 'error';
  downloadUrl: string;
  hasYamlSnapshot: boolean;
  atsStatus: 'idle' | 'analyzing' | 'success' | 'error';
  lastOutputLanguage: 'en' | 'es' | 'unknown';
  auditScores: AuditScores;
  translationMeta: { source_language?: string; target_language?: string; forced?: boolean } | null;
  scoreHistory: ScoreEntry[];
  onReopenYamlEditor: () => void;
  onAudit: () => void;
  onTranslate: () => void;
  onReset: () => void;
};

export function ResultsPanel({
  status,
  downloadUrl,
  hasYamlSnapshot,
  atsStatus,
  lastOutputLanguage,
  auditScores,
  translationMeta,
  scoreHistory,
  onReopenYamlEditor,
  onAudit,
  onTranslate,
  onReset,
}: ResultsPanelProps) {
  return (
    <AnimatePresence mode="popLayout">
      {status === 'success' && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95 }}
          className="rm-box p-10 mt-8 mx-auto max-w-3xl transform rotate-1 bg-[#f0fdf4]"
        >
          <div className="space-y-8 flex flex-col items-center text-center">
            <div className="inline-block bg-white rounded-full p-4 border-2 border-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
              <CheckCircle className="w-16 h-16 text-green-600" />
            </div>
            <div>
              <h3 className="text-4xl font-bold font-serif mb-4">Resume Generated!</h3>
              <p className="text-xl text-gray-800">Your tailored, ATS - friendly PDF is ready for review.</p>
            </div>

            {/* Primary CTA: edit the YAML that produced this CV. Sits above
                the secondary action grid so the iteration loop is the most
                discoverable next step after generation. Hidden until the
                first render produces a YAML snapshot. */}
            {hasYamlSnapshot && (
              <button
                onClick={onReopenYamlEditor}
                title="Abre el editor YAML con el contenido que generó este CV"
                className="rm-btn bg-emerald-600 text-white hover:bg-emerald-700 px-8 py-4 text-lg font-bold flex items-center gap-3 w-full md:w-auto"
              >
                <Code2 className="w-5 h-5" />
                ✏️ Editar YAML directamente
              </button>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
              <a
                href={downloadUrl}
                target="_blank"
                rel="noreferrer"
                className="rm-btn bg-white hover:bg-gray-50 flex justify-center items-center gap-3 px-6 py-4 text-base font-bold"
              >
                <Eye className="w-5 h-5" /> PREVIEW
              </a>

              <a
                href={downloadUrl}
                download="Tailored_Resume.pdf"
                target="_blank"
                className="rm-btn bg-orange-500 text-white hover:bg-orange-600 flex justify-center items-center gap-3 px-6 py-4 text-base font-bold"
              >
                <Download className="w-5 h-5" /> DOWNLOAD PDF
              </a>

              {/* Manual ATS & AI Validation Button */}
              <button
                onClick={onAudit}
                disabled={atsStatus === 'analyzing'}
                className="rm-btn bg-yellow-400 text-black hover:bg-yellow-500 flex justify-center items-center gap-3 px-6 py-4 text-base font-bold"
              >
                <BarChart3 className="w-5 h-5" />
                {atsStatus === 'analyzing' ? 'ANALIZANDO ATS & IA...' : '📊 AUDITAR MATCH ATS & DETECCIÓN IA'}
              </button>

              {/* Translate to English — only renders after a successful generation.
                  Disabled when the last output is already English or while a generation is in flight. */}
              <button
                onClick={onTranslate}
                disabled={lastOutputLanguage === 'en'}
                title={
                  lastOutputLanguage === 'en' ? 'CV already in English' : 'This may take 30-90s'
                }
                className="rm-btn bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-3 px-6 py-4 text-base font-bold"
              >
                <Languages className="w-5 h-5" />
                Translate to English
              </button>

              {/* Reset Button */}
              <button
                onClick={onReset}
                title="Reiniciar todo y borrar CVs generados"
                className="rm-btn bg-rose-50 hover:bg-rose-100 border-rose-600 text-rose-800 md:col-span-2 flex justify-center items-center gap-2 px-6 py-4 text-base font-bold shadow-[4px_4px_0px_0px_rgba(225,29,72,1)]"
              >
                <RotateCcw className="w-5 h-5 text-rose-600" />
                NUEVO / LIMPIAR
              </button>
            </div>

            {/* Translation re-audit badge — visible only after a forced translation pass.
                Mirrors the visual language of the existing AUDITORÍA ATS & TONO HUMANO block
                but is compact and inline. REQ-4 + REQ-7 disable-state wires here. */}
            {auditScores && translationMeta?.forced && lastOutputLanguage === 'en' && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="rm-box p-4 bg-white border-2 border-emerald-600 inline-flex items-center gap-4"
              >
                <span className="font-mono font-bold text-xs uppercase text-emerald-900 tracking-wider">
                  Re-audit (EN)
                </span>
                <span
                  className={`text-3xl font-black font-mono ${(auditScores.ats_score ?? 0) >= 80 ? 'text-green-600' : (auditScores.ats_score ?? 0) >= 60 ? 'text-yellow-600' : 'text-red-600'}`}
                >
                  ATS: {auditScores.ats_score ?? '-'}
                </span>
                <span className="text-gray-300">|</span>
                <span
                  className={`text-3xl font-black font-mono ${(auditScores.ai_detection_score ?? 0) <= 20 ? 'text-green-600' : (auditScores.ai_detection_score ?? 0) <= 50 ? 'text-yellow-600' : 'text-red-600'}`}
                >
                  IA: {auditScores.ai_detection_score ?? '-'}
                </span>
                {auditScores.match_level && (
                  <span className="rm-tag bg-black text-white text-xs px-3 py-1 font-bold">
                    Nivel {auditScores.match_level}
                  </span>
                )}
              </motion.div>
            )}

            {/* Score evolution across refinement passes. */}
            <ScoreHistory entries={scoreHistory} />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default ResultsPanel;