import { AnimatePresence, motion } from 'framer-motion';
import {
  CheckCircle, Eye, Download, BarChart3, Languages, RotateCcw, Code2,
} from 'lucide-react';
import { ScoreHistory } from './ScoreHistory';
import type { ScoreEntry } from '../hooks/useAudit';

/**
 * ResultsPanel — T8 of the UX refactor (specs S4, S8).
 *
 * Success card shown BELOW the main flow once a PDF is ready. It never
 * replaces the form — the user can keep tweaking the inputs and generate
 * again. After the T7 ActionBar simplification this panel is also the home
 * of every secondary action (preview, download, audit, translate, reset).
 *
 * Visual hierarchy:
 *   1. Headline + check icon (celebration)
 *   2. Primary CTA — "Editar YAML directamente" (iteration loop) when a
 *      YAML snapshot is available
 *   3. Download group — PREVIEW + DOWNLOAD PDF (paired actions)
 *   4. Audit group — AUDITAR ATS + Translate to English (re-run CV)
 *   5. Reset — full-width secondary, only when the user wants a clean slate
 *   6. Score history timeline (only if there's history to show)
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
          className="rm-box p-8 md:p-10 bg-[#f0fdf4] space-y-6"
        >
          {/* 1. Headline */}
          <div className="flex items-center gap-4">
            <div className="shrink-0 bg-white rounded-full p-3 border-2 border-black shadow-[3px_3px_0px_0px_rgba(0,0,0,1)]">
              <CheckCircle className="w-10 h-10 text-green-600" />
            </div>
            <div>
              <h3 className="text-2xl md:text-3xl font-bold font-serif">¡CV generado!</h3>
              <p className="text-sm md:text-base text-gray-700">
                Tu PDF adaptado y ATS-friendly está listo para revisar.
              </p>
            </div>
          </div>

          {/* 2. Primary CTA — edit the YAML that produced this CV */}
          {hasYamlSnapshot && (
            <button
              onClick={onReopenYamlEditor}
              title="Abre el editor YAML con el contenido que generó este CV"
              className="rm-btn w-full bg-emerald-600 text-white hover:bg-emerald-700 px-6 py-4 text-base font-bold flex items-center justify-center gap-3"
            >
              <Code2 className="w-5 h-5" />
              ✏️ Editar YAML directamente
            </button>
          )}

          {/* 3. Download group */}
          <div className="grid grid-cols-2 gap-3">
            <a
              href={downloadUrl}
              target="_blank"
              rel="noreferrer"
              className="rm-btn bg-white hover:bg-gray-50 flex justify-center items-center gap-2 px-4 py-3 text-sm font-bold"
            >
              <Eye className="w-4 h-4" /> Preview
            </a>
            <a
              href={downloadUrl}
              download="Tailored_Resume.pdf"
              target="_blank"
              className="rm-btn bg-orange-500 text-white hover:bg-orange-600 flex justify-center items-center gap-2 px-4 py-3 text-sm font-bold"
            >
              <Download className="w-4 h-4" /> Descargar PDF
            </a>
          </div>

          {/* 4. Audit + translate (re-run the pipeline) */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={onAudit}
              disabled={atsStatus === 'analyzing'}
              className="rm-btn bg-yellow-400 text-black hover:bg-yellow-500 disabled:opacity-60 disabled:cursor-not-allowed flex justify-center items-center gap-2 px-4 py-3 text-sm font-bold"
            >
              <BarChart3 className="w-4 h-4" />
              {atsStatus === 'analyzing' ? 'Auditando…' : 'Auditar ATS & IA'}
            </button>
            <button
              onClick={onTranslate}
              disabled={lastOutputLanguage === 'en'}
              title={
                lastOutputLanguage === 'en'
                  ? 'CV already in English'
                  : 'This may take 30-90s'
              }
              className="rm-btn bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2 px-4 py-3 text-sm font-bold"
            >
              <Languages className="w-4 h-4" />
              {lastOutputLanguage === 'en' ? 'Ya en inglés' : 'Traducir a inglés'}
            </button>
          </div>

          {/* 5. Reset */}
          <button
            onClick={onReset}
            className="rm-btn w-full bg-rose-50 hover:bg-rose-100 border-rose-600 text-rose-800 flex justify-center items-center gap-2 px-4 py-2.5 text-xs font-bold shadow-[2px_2px_0px_0px_rgba(225,29,72,1)]"
          >
            <RotateCcw className="w-4 h-4 text-rose-600" />
            Nuevo / Limpiar
          </button>

          {/* 6. Inline re-audit badge after a forced translation pass */}
          {auditScores && translationMeta?.forced && lastOutputLanguage === 'en' && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="rm-box p-3 bg-white border-2 border-emerald-600 flex flex-wrap items-center justify-center gap-3"
            >
              <span className="font-mono font-bold text-[10px] uppercase text-emerald-900 tracking-wider">
                Re-audit (EN)
              </span>
              <span
                className={`text-2xl font-black font-mono ${(auditScores.ats_score ?? 0) >= 80 ? 'text-green-600' : (auditScores.ats_score ?? 0) >= 60 ? 'text-yellow-600' : 'text-red-600'}`}
              >
                ATS: {auditScores.ats_score ?? '-'}
              </span>
              <span className="text-gray-300">|</span>
              <span
                className={`text-2xl font-black font-mono ${(auditScores.ai_detection_score ?? 0) <= 20 ? 'text-green-600' : (auditScores.ai_detection_score ?? 0) <= 50 ? 'text-yellow-600' : 'text-red-600'}`}
              >
                IA: {auditScores.ai_detection_score ?? '-'}
              </span>
              {auditScores.match_level && (
                <span className="rm-tag bg-black text-white text-[10px] px-2 py-0.5 font-bold">
                  {auditScores.match_level}
                </span>
              )}
            </motion.div>
          )}

          {/* 7. Score evolution across refinement passes */}
          <ScoreHistory entries={scoreHistory} />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default ResultsPanel;
