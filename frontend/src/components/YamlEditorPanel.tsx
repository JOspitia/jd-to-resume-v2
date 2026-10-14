import { AnimatePresence, motion } from 'framer-motion';
import { Play, RefreshCw, ShieldCheck, Sparkles, X } from 'lucide-react';

/**
 * YamlEditorPanel — T12 of the UX refactor (specs S5, S6).
 *
 * Full-width contextual panel that slides *over* the main flow (never a new
 * page): the user keeps the context of the form behind the dimmed backdrop
 * and closes the editor with ✕ to go back without losing anything.
 *
 * Rendered when the backend emitted a `yaml_ready` event. The user edits the
 * YAML in the textarea and either POSTs to /api/render-from-yaml or
 * /api/analyze-yaml via the buttons below.
 */

export type YamlEditorPanelProps = {
  yamlContent: string | null;
  /** Panel visibility flag (the `yaml_ready` gate from the SSE stream). */
  yamlReady: boolean;
  onYamlChange: (value: string) => void;
  yamlError: string;
  yamlRepairing: boolean;
  yamlRepairNotice: string;
  status: 'idle' | 'generating' | 'success' | 'error';
  atsStatus: 'idle' | 'analyzing' | 'success' | 'error';
  onRender: () => void;
  onRegenerate: () => void;
  onAudit: () => void;
  onRepair: () => void;
  onClose: () => void;
};

export function YamlEditorPanel({
  yamlContent,
  yamlReady,
  onYamlChange,
  yamlError,
  yamlRepairing,
  yamlRepairNotice,
  status,
  atsStatus,
  onRender,
  onRegenerate,
  onAudit,
  onRepair,
  onClose,
}: YamlEditorPanelProps) {
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
            className="rm-box p-8 mt-8 bg-white w-full max-w-4xl"
          >
            <div className="flex items-center justify-between mb-4 border-b-2 border-black pb-3">
              <h3 className="text-2xl font-bold font-serif">Editor de YAML</h3>
              <button
                type="button"
                onClick={onClose}
                title="Cerrar el editor y volver al CV generado"
                className="text-sm font-mono text-gray-600 hover:text-rose-700 flex items-center gap-1"
              >
                <X className="w-4 h-4" /> Cerrar
              </button>
            </div>

            {yamlError && (
              <div className="mb-4 p-3 bg-rose-100 border-2 border-rose-700 text-rose-900 font-mono text-sm">
                {yamlError}
              </div>
            )}

            <textarea
              value={yamlContent}
              onChange={(e) => onYamlChange(e.target.value)}
              spellCheck={false}
              className="w-full font-mono text-sm p-3 border-2 border-black min-h-[420px] resize-y bg-gray-50 focus:bg-white"
              placeholder="# YAML listo para revisión. Editá libremente y luego presioná 'Generar CV'."
            />

            <div className="flex flex-wrap gap-3 mt-5">
              <button
                type="button"
                onClick={onRender}
                disabled={status === 'generating'}
                className={`rm-btn bg-blue-700 text-white px-6 py-3 font-bold flex items-center gap-2 ${status === 'generating' ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <Play className="w-4 h-4" />
                Generar CV
              </button>
              <button
                type="button"
                onClick={onRegenerate}
                disabled={status === 'generating'}
                className={`rm-btn bg-white border-2 border-black text-black px-6 py-3 font-bold flex items-center gap-2 ${status === 'generating' ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <RefreshCw className="w-4 h-4" />
                Descartar y regenerar YAML
              </button>
              <button
                type="button"
                onClick={onAudit}
                disabled={atsStatus === 'analyzing'}
                className={`rm-btn bg-yellow-100 border-2 border-black text-black px-6 py-3 font-bold flex items-center gap-2 ${atsStatus === 'analyzing' ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <ShieldCheck className="w-4 h-4" />
                VALIDAR YAML (Sin generar CV)
              </button>
              <button
                type="button"
                onClick={onRepair}
                disabled={yamlRepairing}
                title="Pide a la IA que arregle la sintaxis/estructura del YAML sin modificar los datos factuales"
                className={`rm-btn bg-purple-100 border-2 border-purple-700 text-purple-900 px-6 py-3 font-bold flex items-center gap-2 ${yamlRepairing ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <Sparkles className="w-4 h-4" />
                {yamlRepairing ? 'REPARANDO YAML…' : 'REPARAR YAML (IA)'}
              </button>
            </div>

            {yamlRepairNotice && (
              <div className="mt-4 p-3 bg-purple-50 border-2 border-purple-400 text-purple-900 text-xs whitespace-pre-line font-mono">
                {yamlRepairNotice}
              </div>
            )}

            <p className="mt-4 text-xs font-mono text-gray-500">
              El backend usa la YAML exactamente como está acá para renderizar. Si el YAML no es válido el endpoint
              devuelve HTTP 400 con el error del parser.
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default YamlEditorPanel;