import { AnimatePresence, motion } from 'framer-motion';
import { ShieldCheck, BarChart3, AlertCircle, CheckCircle2, AlertTriangle, Sparkles, Edit3, RefreshCw } from 'lucide-react';

/**
 * AuditPanel — T13 of the UX refactor (specs S4, S6).
 *
 * `/api/analyze-ats` + `/api/analyze-yaml` results: the three scores, the
 * matched / missing keyword comparison and the selectable humanization +
 * actionable tips that feed the next regeneration pass.
 */

export type AuditPanelProps = {
  atsStatus: 'idle' | 'analyzing' | 'success' | 'error';
  atsData: any | null;
  atsErrorMessage: string;
  selectedKeywords: string[];
  onToggleKeyword: (keyword: string) => void;
  selectedTips: string[];
  onToggleTip: (tip: string) => void;
  status: 'idle' | 'generating' | 'success' | 'error';
  strictEditsOnly: boolean;
  onStrictEditsOnlyChange: (checked: boolean) => void;
  onRegenerateWithFeedback: () => void;
};

export function AuditPanel({
  atsStatus,
  atsData,
  atsErrorMessage,
  selectedKeywords,
  onToggleKeyword,
  selectedTips,
  onToggleTip,
  status,
  strictEditsOnly,
  onStrictEditsOnlyChange,
  onRegenerateWithFeedback,
}: AuditPanelProps) {
  return (
    <AnimatePresence>
      {atsStatus !== 'idle' && (
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95 }}
          className="rm-box p-8 md:p-10 bg-card border-4 border-border relative"
        >
          <div className="absolute -top-4 -left-4 rm-tag bg-warning text-foreground px-4 py-2 text-lg font-black flex items-center gap-2">
            <ShieldCheck className="w-5 h-5" /> AUDITORÍA ATS &amp; TONO HUMANO(CompuTrabajo Style)
          </div>

          {atsStatus === 'analyzing' && (
            <div className="py-12 flex flex-col items-center justify-center space-y-4">
              <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }}>
                <BarChart3 className="w-16 h-16 text-primary" />
              </motion.div>
              <p className="text-xl font-bold font-serif">
                Analizando palabras clave, coincidencia ATS y nivel de redacción por IA...
              </p>
            </div>
          )}

          {atsStatus === 'error' && (
            <div className="p-6 bg-red-50 border-2 border-red-500 text-red-700 rounded-none flex items-center gap-4">
              <AlertCircle className="w-10 h-10 shrink-0" />
              <div>
                <h4 className="font-bold text-lg">Error en Auditoría ATS</h4>
                <p>{atsErrorMessage}</p>
              </div>
            </div>
          )}

          {atsStatus === 'success' && atsData && (
            <div className="space-y-10 mt-4">
              {/* Scores Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* ATS Match Score */}
                <div className="rm-box p-6 bg-primary/15 text-center flex flex-col items-center justify-center">
                  <span className="font-mono font-bold text-xs uppercase text-blue-900 tracking-wider mb-2">
                    Match ATS(CompuTrabajo)
                  </span>
                  <div
                    className={`text-6xl font-black font-mono my-2 ${atsData.ats_score >= 80 ? 'text-green-600' : atsData.ats_score >= 60 ? 'text-warning' : 'text-red-600'}`}
                  >
                    {atsData.ats_score} %
                  </div>
                  <span className="rm-tag bg-foreground text-background text-xs px-3 py-1 font-bold">
                    Nivel {atsData.match_level || 'Medio'}
                  </span>
                </div>

                {/* AI Tone / Human Risk Score */}
                <div className="rm-box p-6 bg-accent/15 text-center flex flex-col items-center justify-center">
                  <span className="font-mono font-bold text-xs uppercase text-foreground tracking-wider mb-2">
                    Detección de Tono IA
                  </span>
                  <div
                    className={`text-6xl font-black font-mono my-2 ${atsData.ai_detection_score <= 20 ? 'text-green-600' : atsData.ai_detection_score <= 50 ? 'text-warning' : 'text-red-600'}`}
                  >
                    {atsData.ai_detection_score} %
                  </div>
                  <span className="text-xs font-bold text-gray-800 px-2 py-1">
                    {atsData.ai_tone_verdict || 'Análisis de Redacción'}
                  </span>
                </div>

                {/* ATS Format Score */}
                <div className="rm-box p-6 bg-green-50 text-center flex flex-col items-center justify-center">
                  <span className="font-mono font-bold text-xs uppercase text-green-900 tracking-wider mb-2">
                    Legibilidad &amp; Formato
                  </span>
                  <div className="text-6xl font-black font-mono my-2 text-green-700">
                    {atsData.ats_formatting_score || 95} %
                  </div>
                  <span className="text-xs font-bold text-green-800">1 Página &amp; Estructura Limpia</span>
                </div>
              </div>

              {/* Keywords Comparison */}
              <div className="grid md:grid-cols-2 gap-8">
                {/* Matched Keywords */}
                <div className="rm-box p-6 bg-card">
                  <h4 className="font-bold text-lg font-serif mb-4 flex items-center gap-2 text-green-700">
                    <CheckCircle2 className="w-5 h-5" /> Palabras Clave Detectadas({atsData.matched_keywords?.length || 0})
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {atsData.matched_keywords && atsData.matched_keywords.length > 0 ? (
                      atsData.matched_keywords.map((kw: string, i: number) => (
                        <span
                          key={i}
                          className="rm-tag bg-green-100 border border-green-600 text-green-900 px-3 py-1 font-bold text-sm"
                        >
                          ✓ {kw}
                        </span>
                      ))
                    ) : (
                      <p className="text-muted-foreground text-sm">No se detectaron palabras clave coincidentes.</p>
                    )}
                  </div>
                </div>

                {/* Missing Keywords (Interactive Selection) */}
                <div className="rm-box p-6 bg-card">
                  <div className="flex justify-between items-center mb-2">
                    <h4 className="font-bold text-lg font-serif flex items-center gap-2 text-orange-700">
                      <AlertTriangle className="w-5 h-5" /> Palabras Clave Faltantes({atsData.missing_keywords?.length || 0})
                    </h4>
                    {selectedKeywords.length > 0 && (
                      <span className="rm-tag bg-orange-500 text-white text-xs px-2.5 py-0.5 font-mono font-bold">
                        {selectedKeywords.length} seleccionada(s)
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground font-medium mb-4">
                    💡 Haz clic en las palabras clave que realmente poseas para marcarlas e integrarlas automáticamente al regenerar:
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {atsData.missing_keywords && atsData.missing_keywords.length > 0 ? (
                      atsData.missing_keywords.map((kw: string, i: number) => {
                        const isSelected = selectedKeywords.includes(kw);
                        return (
                          <button
                            key={i}
                            type="button"
                            onClick={() => onToggleKeyword(kw)}
                            className={`rm-tag border text-sm font-bold px-3 py-1.5 transition-all flex items-center gap-1.5 cursor-pointer ${isSelected
                              ? 'bg-orange-500 border-border text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] -translate-y-0.5'
                              : 'bg-orange-50 border-orange-400 text-orange-950 hover:bg-orange-100'}`}
                          >
                            <span>{isSelected ? '✓' : '+'}</span>
                            <span>{kw}</span>
                          </button>
                        );
                      })
                    ) : (
                      <p className="text-muted-foreground text-sm">¡Excelente! No faltan palabras clave principales.</p>
                    )}
                  </div>
                </div>
              </div>

              {/* Selectable AI Humanize & Actionable Tips */}
              <div className="grid md:grid-cols-2 gap-8">
                {/* AI Humanization Feedback */}
                {atsData.ai_humanize_tips && atsData.ai_humanize_tips.length > 0 && (
                  <div className="rm-box p-6 bg-accent/15">
                    <h4 className="font-bold text-lg font-serif mb-2 flex items-center gap-2 text-foreground">
                      <Sparkles className="w-5 h-5 text-foreground" /> Consejos para Humanizar el Tono
                    </h4>
                    <p className="text-xs text-purple-800 font-medium mb-4">
                      Marca las casillas que deseas aplicar al regenerar:
                    </p>
                    <div className="space-y-3">
                      {atsData.ai_humanize_tips.map((tip: string, i: number) => (
                        <label
                          key={i}
                          className="flex items-start gap-3 cursor-pointer p-2 border border-foreground/30 hover:border-foreground/70 bg-card/70 hover:bg-accent transition-all select-none"
                        >
                          <input
                            type="checkbox"
                            checked={selectedTips.includes(tip)}
                            onChange={() => onToggleTip(tip)}
                            className="w-4 h-4 mt-1 accent-purple-700 cursor-pointer shrink-0"
                          />
                          <span className="text-sm font-medium text-foreground">{tip}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {/* Actionable ATS Tips */}
                {atsData.actionable_tips && atsData.actionable_tips.length > 0 && (
                  <div className="rm-box p-6 bg-warning/15">
                    <h4 className="font-bold text-lg font-serif mb-2 flex items-center gap-2 text-yellow-900">
                      <BarChart3 className="w-5 h-5 text-yellow-800" /> Recomendaciones para Subir de Rango
                    </h4>
                    <p className="text-xs text-yellow-800 font-medium mb-4">
                      Marca las casillas que deseas aplicar al regenerar:
                    </p>
                    <div className="space-y-3">
                      {atsData.actionable_tips.map((tip: string, i: number) => (
                        <label
                          key={i}
                          className="flex items-start gap-3 cursor-pointer p-2 border border-warning hover:border-warning bg-card/70 hover:bg-accent transition-all select-none"
                        >
                          <input
                            type="checkbox"
                            checked={selectedTips.includes(tip)}
                            onChange={() => onToggleTip(tip)}
                            className="w-4 h-4 mt-1 accent-warning cursor-pointer shrink-0"
                          />
                          <span className="text-sm font-medium text-foreground">{tip}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Refinement Area: selections + optional extra instructions + regeneration button */}
              <div className="rm-box p-6 md:p-8 bg-primary/15 border-2 border-border space-y-4">
                <h4 className="font-bold text-xl font-serif flex items-center gap-2 text-blue-900">
                  <Edit3 className="w-6 h-6 text-primary" /> Ajustar &amp; Regenerar CV con Mejoras Seleccionadas
                </h4>
                <p className="text-sm text-muted-foreground font-medium">
                  Has seleccionado <span className="font-bold text-orange-700">{selectedKeywords.length} palabra(s) clave</span> y{' '}
                  <span className="font-bold text-purple-800">{selectedTips.length} consejo(s)</span>. Las indicaciones
                  adicionales se escriben en «Opciones Avanzadas → Instrucciones adicionales para la IA».
                </p>

                {/* Strict Surgical Edit Toggle */}
                <label className="flex items-start gap-3 bg-card border-2 border-border p-4 cursor-pointer hover:bg-warning/15 transition-all select-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                  <input
                    type="checkbox"
                    checked={strictEditsOnly}
                    onChange={(e) => onStrictEditsOnlyChange(e.target.checked)}
                    className="w-5 h-5 mt-0.5 accent-warning cursor-pointer shrink-0"
                  />
                  <div>
                    <span className="font-bold text-sm block text-foreground">
                      🔒 Modo Edición Quirúrgica(Aplicar SOLO cambios solicitados)
                    </span>
                    <span className="text-xs text-muted-foreground block mt-0.5 font-medium">
                      Activa esta casilla para corregir o cambiar datos puntuales(ej.cambiar fecha de la UNIR a "2026-08 -
                      Actualidad") garantizando que la IA conserve el resto del CV 100 % idéntico sin reescribir ni alterar
                      nada más.
                    </span>
                  </div>
                </label>

                <div className="flex justify-end pt-2">
                  <button
                    onClick={onRegenerateWithFeedback}
                    disabled={status === 'generating'}
                    className="rm-btn bg-accent-foreground text-white hover:bg-purple-800 disabled:opacity-50 px-8 py-4 text-lg font-bold flex items-center gap-3"
                  >
                    <RefreshCw className={`w-5 h-5 ${status === 'generating' ? 'animate-spin' : ''}`} />
                    {status === 'generating' ? 'REGENERANDO CV...' : '🔄 REGENERAR CV CON MEJORAS SELECCIONADAS'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default AuditPanel;