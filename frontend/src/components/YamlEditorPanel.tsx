import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Play, RefreshCw, ShieldCheck, Sparkles, X, RotateCcw,
  AlertCircle, CheckCircle2, FileText, LayoutGrid,
} from 'lucide-react';

import { validateYaml } from '../lib/yamlValidator';
import {
  emptyFormData,
  parseYamlToFormData,
  serializeFormDataToYaml,
  type YamlFormData,
} from '../lib/yamlFormData';
import { YamlFormEditor } from './YamlFormEditor';

/**
 * YamlEditorPanel — T2/T3 of feat/yaml-editor-structured + T2 of
 * odd/tasks/yaml-editor-validation.md.
 *
 * Hybrid form + raw YAML editor with a toggle. The user edits fields, not
 * YAML text — no stray colons, no indentation accidents, no syntax errors.
 *
 * View modes:
 *   - 'form' (default): structured fields, one section per top-level key.
 *     Add/Remove buttons for lists. The form is the source of truth.
 *   - 'yaml' (toggle): the existing raw YAML textarea. Editable, for power
 *     users who want to see the wire format.
 *
 * Sync model: formData is local state. When the user edits the form we
 * serialize and call onYamlChange. When yamlContent changes from outside
 * (SSE event, auto-repair, parent re-render) we re-parse into formData.
 * A ref guards against the re-parse firing on our own form-derived update.
 *
 * The existing auto-cleanup (validate + auto-repair on Generate) and the
 * REPARAR / VALIDAR / Generar CV buttons still work — they operate on
 * yamlContent, which is always the serialized form.
 */

export type YamlEditorPanelProps = {
  yamlContent: string | null;
  yamlReady: boolean;
  onYamlChange: (value: string) => void;
  yamlError: string;
  yamlRepairing: boolean;
  yamlRepairNotice: string;
  hasBackup: boolean;
  status: 'idle' | 'generating' | 'success' | 'error';
  atsStatus: 'idle' | 'analyzing' | 'success' | 'error';
  onRender: () => void;
  onRegenerate: () => void;
  onAudit: () => void;
  onRepair: () => void;
  onRestoreBackup: () => void;
  onClose: () => void;
};

type ViewMode = 'form' | 'yaml';

export function YamlEditorPanel({
  yamlContent,
  yamlReady,
  onYamlChange,
  yamlError,
  yamlRepairing,
  yamlRepairNotice,
  hasBackup,
  status,
  atsStatus,
  onRender,
  onRegenerate,
  onAudit,
  onRepair,
  onRestoreBackup,
  onClose,
}: YamlEditorPanelProps) {
  // ---------- Form state ----------
  const [formData, setFormData] = useState<YamlFormData>(() =>
    yamlContent ? parseYamlToFormData(yamlContent) : emptyFormData(),
  );
  const [viewMode, setViewMode] = useState<ViewMode>('form');

  // Guard against the sync effect firing on our own form-derived update.
  const isInternalUpdate = useRef(false);

  // Re-parse when yamlContent changes from outside (initial load, auto-repair,
  // SSE event). Skip when the change came from our own form serialization.
  useEffect(() => {
    if (!yamlContent) return;
    if (isInternalUpdate.current) {
      isInternalUpdate.current = false;
      return;
    }
    setFormData(parseYamlToFormData(yamlContent));
  }, [yamlContent]);

  const handleFormChange = (next: YamlFormData) => {
    setFormData(next);
    isInternalUpdate.current = true;
    onYamlChange(serializeFormDataToYaml(next));
  };

  const handleYamlTextChange = (next: string) => {
    // Direct yamlContent update — the useEffect re-parses to formData so the
    // form view stays in sync if the user switches back.
    isInternalUpdate.current = true;
    onYamlChange(next);
    setFormData(parseYamlToFormData(next));
  };

  // ---------- Live validation (from the previous branch) ----------
  const validation = useMemo(
    () => (yamlContent ? validateYaml(yamlContent) : { valid: true }),
    [yamlContent],
  );

  const textareaClass = validation.valid
    ? 'w-full font-mono text-sm p-3 border-2 border-success min-h-[420px] resize-y bg-card'
    : 'w-full font-mono text-sm p-3 border-2 border-destructive min-h-[420px] resize-y bg-destructive/10/30';

  // ---------- Render ----------
  return (
    <AnimatePresence>
      {yamlReady && yamlContent && (
        <motion.div
          key="yaml-editor-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 overflow-y-auto bg-black/50 p-4 md:p-8 flex items-start justify-center"
        >
          <motion.div
            key="yaml-editor-panel"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="rm-box p-8 mt-8 bg-card w-full max-w-4xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-4 border-b-2 border-border pb-3 flex-wrap gap-2">
              <div className="flex items-center gap-3">
                <h3 className="text-2xl font-bold font-serif">Editor de CV</h3>
                {validation.valid ? (
                  <span className="flex items-center gap-1 text-xs font-mono text-success">
                    <CheckCircle2 className="w-4 h-4" /> YAML válido
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs font-mono text-destructive">
                    <AlertCircle className="w-4 h-4" /> YAML inválido
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                {/* View-mode toggle */}
                <div className="flex border-2 border-border">
                  <button
                    type="button"
                    onClick={() => setViewMode('form')}
                    aria-pressed={viewMode === 'form'}
                    className={`px-3 py-1.5 text-xs font-bold flex items-center gap-1 ${viewMode === 'form' ? 'bg-foreground text-background' : 'bg-card text-foreground'}`}
                  >
                    <LayoutGrid className="w-3.5 h-3.5" /> Formulario
                  </button>
                  <button
                    type="button"
                    onClick={() => setViewMode('yaml')}
                    aria-pressed={viewMode === 'yaml'}
                    className={`px-3 py-1.5 text-xs font-bold flex items-center gap-1 ${viewMode === 'yaml' ? 'bg-foreground text-background' : 'bg-card text-foreground'}`}
                  >
                    <FileText className="w-3.5 h-3.5" /> Ver YAML
                  </button>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  title="Cerrar el editor y volver al CV generado"
                  className="text-sm font-mono text-muted-foreground hover:text-destructive flex items-center gap-1"
                >
                  <X className="w-4 h-4" /> Cerrar
                </button>
              </div>
            </div>

            {/* Error banner (from the parent, e.g. backend render error) */}
            {yamlError && (
              <div className="mb-4 p-3 bg-destructive/15 border-2 border-rose-700 text-destructive font-mono text-sm">
                {yamlError}
              </div>
            )}

            {/* Inline validation error with line/column (yaml view) */}
            {viewMode === 'yaml' && !validation.valid && (
              <div className="mb-3 p-3 bg-destructive/10 border-2 border-rose-500 text-destructive font-mono text-xs">
                <div className="flex items-center gap-1 font-bold mb-1">
                  <AlertCircle className="w-3.5 h-3.5" /> Error de sintaxis YAML
                  {validation.line !== undefined && (
                    <span className="ml-2 text-rose-600">
                      (línea {validation.line}
                      {validation.column !== undefined ? `, columna ${validation.column}` : ''})
                    </span>
                  )}
                </div>
                <div className="text-destructive">{validation.error}</div>
              </div>
            )}

            {/* Body — form or yaml depending on viewMode */}
            {viewMode === 'form' ? (
              <YamlFormEditor formData={formData} onChange={handleFormChange} />
            ) : (
              <>
                <textarea
                  value={yamlContent}
                  onChange={(e) => handleYamlTextChange(e.target.value)}
                  spellCheck={false}
                  className={textareaClass}
                  placeholder="# YAML listo para revisión..."
                  aria-invalid={!validation.valid}
                  aria-describedby="yaml-validation-status"
                />
                <div id="yaml-validation-status" className="sr-only">
                  {validation.valid
                    ? 'YAML válido'
                    : `YAML inválido: ${validation.error ?? ''}`}
                </div>
              </>
            )}

            {/* Auto-repair banner — shown while `Generar CV` is transparently
                fixing a broken YAML so the user knows why there's a delay and
                that nothing was lost. */}
            {yamlRepairing && status === 'generating' && (
              <div className="mt-4 p-3 bg-accent/15 border-2 border-purple-400 text-foreground text-sm flex items-center gap-3">
                <Sparkles className="w-4 h-4 shrink-0 animate-pulse" />
                <span>
                  Detectamos un error de formato en tu YAML. La IA lo está
                  reparando automáticamente antes de generar el CV — no perdiste nada.
                </span>
              </div>
            )}

            {/* Action row — unchanged from the previous branch */}
            <div className="flex flex-wrap gap-3 mt-5">
              <button
                type="button"
                onClick={onRender}
                disabled={status === 'generating'}
                title={
                  !validation.valid
                    ? 'El YAML tiene errores. La IA los arreglará automáticamente al hacer clic.'
                    : undefined
                }
                className={`rm-btn bg-primary text-white px-6 py-3 font-bold flex items-center gap-2 ${status === 'generating' ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <Play className="w-4 h-4" />
                {status === 'generating' ? 'Renderizando…' : 'Generar CV'}
              </button>
              <button
                type="button"
                onClick={onRegenerate}
                disabled={status === 'generating'}
                className={`rm-btn bg-card border-2 border-border text-foreground px-6 py-3 font-bold flex items-center gap-2 ${status === 'generating' ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <RefreshCw className="w-4 h-4" />
                Descartar y regenerar YAML
              </button>
              <button
                type="button"
                onClick={onAudit}
                disabled={atsStatus === 'analyzing'}
                className={`rm-btn bg-warning/15 border-2 border-border text-foreground px-6 py-3 font-bold flex items-center gap-2 ${atsStatus === 'analyzing' ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <ShieldCheck className="w-4 h-4" />
                VALIDAR YAML (Sin generar CV)
              </button>
              <button
                type="button"
                onClick={onRepair}
                disabled={yamlRepairing}
                title="Pide a la IA que arregle la sintaxis/estructura del YAML preservando tus datos verbatim"
                className={`rm-btn bg-accent border-2 border-foreground/50 text-foreground px-6 py-3 font-bold flex items-center gap-2 ${yamlRepairing ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <Sparkles className="w-4 h-4" />
                {yamlRepairing ? 'REPARANDO YAML…' : 'REPARAR YAML (IA)'}
              </button>
              {hasBackup && (
                <button
                  type="button"
                  onClick={onRestoreBackup}
                  title="Restaura el texto que tenías antes de la última reparación"
                  className="rm-btn bg-card border-2 border-foreground/50 text-foreground px-6 py-3 font-bold flex items-center gap-2"
                >
                  <RotateCcw className="w-4 h-4" />
                  Deshacer reparación
                </button>
              )}
            </div>

            {yamlRepairNotice && (
              <div className="mt-4 p-3 bg-accent/15 border-2 border-purple-400 text-foreground text-xs whitespace-pre-line font-mono">
                {yamlRepairNotice}
              </div>
            )}

            <p className="mt-4 text-xs font-mono text-muted-foreground">
              {viewMode === 'form'
                ? 'Estás editando el formulario. Los cambios se serializan a YAML automáticamente. Si preferís ver el YAML crudo, usá el toggle "Ver YAML" arriba.'
                : 'Estás editando el YAML crudo. Si preferís un formulario con campos, usá el toggle "Formulario" arriba.'}
            </p>

            {/* Explicit contract for this route. The AI-tailoring path (JD /
                "Requerimientos de modificación") is a different flow entirely;
                here the document is the user's, and nothing rewrites it. */}
            <div className="mt-3 p-3 bg-emerald-50 border-2 border-success text-success text-xs">
              <span className="font-bold">Tu texto se genera tal cual.</span>{' '}
              Al presionar "Generar CV" no se llama a la IA para reescribir nada: se
              renderiza exactamente lo que escribiste. Si el formato tiene un error,
              la IA solo corrige la estructura (indentación, comillas, listas) y el
              sistema verifica que no haya cambiado ni una palabra — si lo hace,
              devuelve tu texto original sin tocar.
              <span className="block mt-1.5 opacity-80">
                Para que la IA <em>reescriba</em> el CV usá "GENERATE TAILORED RESUME"
                con una oferta o con "Requerimientos de modificación".
              </span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default YamlEditorPanel;
