import { AnimatePresence, motion } from 'framer-motion';
import {
  CheckCircle, Eye, Download, BarChart3, Languages, RotateCcw, Code2,
} from 'lucide-react';
import { ScoreHistory } from './ScoreHistory';
import type { ScoreEntry } from '../hooks/useAudit';

import { Card } from './ui/Card';
import { Button, buttonVariants } from './ui/Button';
import { Badge } from './ui/Badge';

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
 *
 * PR5 polish: migrated all rm-* classes to <Card> / <Button> / <Badge>
 * primitives + buttonVariants() helper for the inline anchors (preview /
 * download). Semantic colors now flow from the token system so the
 * dark mode toggle (PR6) will re-tint without touching this file.
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
        <Card
          variant="success"
          size="xl"
          className="space-y-6"
        >
          {/* 1. Headline */}
          <div className="flex items-center gap-4">
            <div className="shrink-0 bg-card rounded-full p-3 border-2 border-border shadow-neo">
              <CheckCircle className="w-10 h-10 text-success" aria-hidden="true" />
            </div>
            <div>
              <h3 className="text-2xl md:text-3xl font-bold font-serif">¡CV generado!</h3>
              <p className="text-sm md:text-base text-muted-foreground">
                Tu PDF adaptado y ATS-friendly está listo para revisar.
              </p>
            </div>
          </div>

          {/* 2. Primary CTA — edit the YAML that produced this CV */}
          {hasYamlSnapshot && (
            <Button
              onClick={onReopenYamlEditor}
              variant="success"
              size="md"
              className="w-full"
              aria-label="Abre el editor YAML con el contenido que generó este CV"
            >
              <Code2 className="w-5 h-5" aria-hidden="true" />
              ✏️ Editar YAML directamente
            </Button>
          )}

          {/* 3. Download group */}
          <div className="grid grid-cols-2 gap-3">
            <a
              href={`${downloadUrl}${downloadUrl.includes('?') ? '&' : '?'}inline=1`}
              target="_blank"
              rel="noreferrer"
              aria-label="Previsualizar el PDF generado"
              className={buttonVariants({ variant: 'outline', size: 'md' })}
            >
              <Eye className="w-4 h-4" aria-hidden="true" /> Preview
            </a>
            <a
              href={downloadUrl}
              download="Tailored_Resume.pdf"
              target="_blank"
              aria-label="Descargar el PDF generado"
              className={buttonVariants({ variant: 'secondary', size: 'md' })}
            >
              <Download className="w-4 h-4" aria-hidden="true" /> Descargar PDF
            </a>
          </div>

          {/* 4. Audit + translate (re-run the pipeline) */}
          <div className="grid grid-cols-2 gap-3">
            <Button
              onClick={onAudit}
              disabled={atsStatus === 'analyzing'}
              variant="warning"
              size="md"
              aria-label="Ejecutar auditoría ATS e IA sobre el CV generado"
            >
              <BarChart3 className="w-4 h-4" aria-hidden="true" />
              {atsStatus === 'analyzing' ? 'Auditando…' : 'Auditar ATS & IA'}
            </Button>
            <Button
              onClick={onTranslate}
              disabled={lastOutputLanguage === 'en'}
              variant="success"
              size="md"
              aria-label={
                lastOutputLanguage === 'en'
                  ? 'El CV ya está en inglés'
                  : 'Traducir el CV al inglés (puede tomar 30-90 segundos)'
              }
            >
              <Languages className="w-4 h-4" aria-hidden="true" />
              {lastOutputLanguage === 'en' ? 'Ya en inglés' : 'Traducir a inglés'}
            </Button>
          </div>

          {/* 5. Reset */}
          <Button
            onClick={onReset}
            variant="destructive"
            size="sm"
            className="w-full"
            aria-label="Reiniciar todo el proceso"
          >
            <RotateCcw className="w-4 h-4" aria-hidden="true" />
            Nuevo / Limpiar
          </Button>

          {/* 6. Inline re-audit badge after a forced translation pass */}
          {auditScores && translationMeta?.forced && lastOutputLanguage === 'en' && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-wrap items-center justify-center gap-3 bg-card p-3 border-2 border-success"
              role="group"
              aria-label="Resultados de la re-auditoría tras la traducción"
            >
              <span className="font-mono font-bold text-[10px] uppercase text-foreground tracking-wider">
                Re-audit (EN)
              </span>
              <span
                className={`text-2xl font-black font-mono ${(auditScores.ats_score ?? 0) >= 80 ? 'text-success' : (auditScores.ats_score ?? 0) >= 60 ? 'text-warning' : 'text-destructive'}`}
              >
                ATS: {auditScores.ats_score ?? '-'}
              </span>
              <span className="text-muted-foreground">|</span>
              <span
                className={`text-2xl font-black font-mono ${(auditScores.ai_detection_score ?? 0) <= 20 ? 'text-success' : (auditScores.ai_detection_score ?? 0) <= 50 ? 'text-warning' : 'text-destructive'}`}
              >
                IA: {auditScores.ai_detection_score ?? '-'}
              </span>
              {auditScores.match_level && (
                <Badge variant="default" size="sm" className="text-[10px]">
                  {auditScores.match_level}
                </Badge>
              )}
            </motion.div>
          )}

          {/* 7. Score evolution across refinement passes */}
          <ScoreHistory entries={scoreHistory} />
        </Card>
      )}
    </AnimatePresence>
  );
}

export default ResultsPanel;