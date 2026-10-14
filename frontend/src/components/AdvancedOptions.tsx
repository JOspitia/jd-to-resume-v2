import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown, SlidersHorizontal } from 'lucide-react';
import { useState } from 'react';

/**
 * AdvancedOptions — T8 of the UX refactor (specs S2, S6).
 *
 * Collapsible container for the settings ~80% of users never touch (theme,
 * page-break control, auto ATS validation, edit-before-generate, strict
 * edits, custom prompt). It opens on the first visit — so the options are
 * discoverable once — and then remembers the user's last choice.
 *
 * NOTE: implemented with `framer-motion` + a native button because the
 * project ships no `@radix-ui/react-collapsible` primitive and this refactor
 * adds no dependencies.
 */

/** Remembers the last open/closed choice. Deliberately NOT cleared by "Nuevo / Limpiar". */
const STORAGE_KEY = 'jd-to-resume.advanced-options';

const THEMES = [
  { id: 'sb2nov', name: 'SB2Nov', badge: 'Silicon Valley / ATS', desc: 'Limpio y estructurado para Tech' },
  { id: 'classic', name: 'Classic', badge: 'Sobrio', desc: 'Tradicional, elegante y universal' },
  { id: 'moderncv', name: 'ModernCV', badge: 'Visual', desc: 'Detalles a color y tipografía moderna' },
  { id: 'classic_html', name: 'Classic HTML', badge: 'Playwright', desc: 'Renderizado web tradicional' },
];

export type AdvancedOptionsProps = {
  selectedTheme: string;
  onThemeChange: (theme: string) => void;
  fitSinglePage: boolean;
  onFitSinglePageChange: (checked: boolean) => void;
  pageBreakSection: string;
  onPageBreakSectionChange: (section: string) => void;
  autoValidateATS: boolean;
  onAutoValidateAtsChange: (checked: boolean) => void;
  editBeforeGenerate: boolean;
  onEditBeforeGenerateChange: (checked: boolean) => void;
  strictEditsOnly: boolean;
  onStrictEditsOnlyChange: (checked: boolean) => void;
  customPrompt: string;
  onCustomPromptChange: (value: string) => void;
};

export function AdvancedOptions({
  selectedTheme,
  onThemeChange,
  fitSinglePage,
  onFitSinglePageChange,
  pageBreakSection,
  onPageBreakSectionChange,
  autoValidateATS,
  onAutoValidateAtsChange,
  editBeforeGenerate,
  onEditBeforeGenerateChange,
  strictEditsOnly,
  onStrictEditsOnlyChange,
  customPrompt,
  onCustomPromptChange,
}: AdvancedOptionsProps) {
  const [open, setOpen] = useState(() => {
    try {
      // Open on the very first visit; afterwards honour the user's choice.
      return localStorage.getItem(STORAGE_KEY) !== 'closed';
    } catch {
      return true;
    }
  });

  const toggleOpen = () => {
    const next = !open;
    setOpen(next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? 'open' : 'closed');
    } catch {
      // best-effort: private mode / quota
    }
  };

  return (
    <div className="rm-box p-6 md:p-8 bg-[#F3F4F6] relative">
      <div className="absolute -top-4 -left-4 rm-tag bg-white text-black px-4 py-2 text-lg">OPTIONAL</div>

      <button
        type="button"
        onClick={toggleOpen}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-4 text-left cursor-pointer select-none"
      >
        <span className="flex items-center gap-3">
          <SlidersHorizontal className="w-5 h-5" />
          <span className="text-xl font-bold font-serif">Additional Context &amp; Opciones Avanzadas</span>
        </span>
        <span className="flex items-center gap-2 font-mono text-xs uppercase text-gray-600">
          {open ? 'Ocultar' : 'Mostrar'}
          <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2 }}>
            <ChevronDown className="w-5 h-5" />
          </motion.span>
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="advanced-options"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div className="pt-6 space-y-8">
              {/* Theme Selector */}
              <div>
                <label className="font-bold font-mono text-sm uppercase tracking-wide block mb-3">
                  🎨 Plantilla &amp; Diseñador de PDF(Vectorial Typst / ATS)
                </label>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {THEMES.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => onThemeChange(t.id)}
                      aria-pressed={selectedTheme === t.id}
                      className={`p-3.5 text-left border-2 transition-all flex flex-col justify-between ${selectedTheme === t.id
                        ? 'border-blue-700 bg-blue-50 font-bold shadow-[2px_2px_0px_0px_rgba(29,78,216,1)]'
                        : 'border-black bg-white hover:bg-gray-50'}`}
                    >
                      <div>
                        <span className="text-xs font-mono px-1.5 py-0.5 bg-gray-200 text-black font-bold uppercase inline-block mb-1">
                          {t.badge}
                        </span>
                        <div className="text-sm font-serif font-bold text-black">{t.name}</div>
                      </div>
                      <div className="text-[11px] text-gray-600 mt-2 line-clamp-1">{t.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Page Break & Anti-Orphan Layout Controls */}
              <div className="border-t-2 border-gray-300 pt-6">
                <label className="font-bold font-mono text-sm uppercase tracking-wide block mb-3">
                  📐 Control de Páginas &amp; Saltos Limpios(Evitar líneas huérfanas)
                </label>
                <div className="grid md:grid-cols-2 gap-4">
                  {/* Checkbox: Strict 1 page auto-compact */}
                  <label className="flex items-start gap-3 bg-white border-2 border-black p-4 cursor-pointer hover:bg-gray-50 shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] select-none">
                    <input
                      type="checkbox"
                      checked={fitSinglePage}
                      onChange={(e) => onFitSinglePageChange(e.target.checked)}
                      className="w-5 h-5 mt-0.5 accent-blue-700 cursor-pointer"
                    />
                    <div>
                      <span className="font-bold text-sm block">Ajuste Compacto(Priorizar 1 Página)</span>
                      <span className="text-xs text-gray-600 block mt-0.5">
                        Reduce márgenes e interlineado para evitar que 1 o 2 líneas se desborden a una segunda hoja.
                      </span>
                    </div>
                  </label>

                  {/* Selector: Manual page break before section */}
                  <div className="bg-white border-2 border-black p-4 shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] flex flex-col justify-between">
                    <div>
                      <label className="font-bold text-sm block mb-1">Insertar Salto de Página limpio antes de:</label>
                      <span className="text-xs text-gray-600 block mb-2">
                        Si tu CV es de 2 hojas, divide limpiamente una sección completa al inicio de la página 2.
                      </span>
                    </div>
                    <select
                      value={pageBreakSection}
                      onChange={(e) => onPageBreakSectionChange(e.target.value)}
                      className="w-full border-2 border-black bg-white p-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-600"
                    >
                      <option value="none">Sin salto manual(Automático anti - huérfanas)</option>
                      <option value="Experience">Antes de: Experiencia Laboral(Experience)</option>
                      <option value="Education">Antes de: Educación(Education)</option>
                      <option value="Projects">Antes de: Proyectos(Projects)</option>
                      <option value="Skills">Antes de: Habilidades(Skills)</option>
                      <option value="Achievements">Antes de: Logros(Achievements)</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Pipeline toggles */}
              <div className="border-t-2 border-gray-300 pt-6 space-y-3">
                <label className="flex items-center gap-3 bg-white border-2 border-black p-4 font-mono font-bold cursor-pointer hover:bg-gray-50 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] select-none">
                  <input
                    type="checkbox"
                    checked={autoValidateATS}
                    onChange={(e) => onAutoValidateAtsChange(e.target.checked)}
                    className="w-5 h-5 accent-blue-700 cursor-pointer"
                  />
                  <span className="text-sm md:text-base">Validar automáticamente match ATS al finalizar generación</span>
                </label>

                {/* Edit-before-generate YAML editor checkbox (feat/yaml-editor) */}
                <label className="flex items-center gap-3 bg-white border-2 border-black p-4 font-mono font-bold cursor-pointer hover:bg-gray-50 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] select-none">
                  <input
                    type="checkbox"
                    checked={editBeforeGenerate}
                    onChange={(e) => onEditBeforeGenerateChange(e.target.checked)}
                    className="w-5 h-5 accent-blue-700 cursor-pointer"
                  />
                  <span className="text-sm md:text-base">
                    Editar respuesta de la IA antes de generar el CV (formato YAML)
                  </span>
                </label>
              </div>

              {/* Strict Surgical Edit Toggle */}
              <div className="border-t-2 border-gray-300 pt-6">
                <label className="flex items-start gap-3 bg-yellow-50 border-2 border-black p-3.5 cursor-pointer hover:bg-yellow-100 transition-all select-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                  <input
                    type="checkbox"
                    checked={strictEditsOnly}
                    onChange={(e) => onStrictEditsOnlyChange(e.target.checked)}
                    className="w-5 h-5 mt-0.5 accent-yellow-600 cursor-pointer shrink-0"
                  />
                  <div>
                    <span className="font-bold text-sm block text-black">
                      Modo Edición SOLO cambios solicitados
                    </span>
                    <span className="text-xs text-gray-700 block mt-0.5 font-medium">
                      Actívalo para realizar ajustes puntuales sin modificar ni reescribir nada más de tu CV.
                    </span>
                  </div>
                </label>
              </div>

              {/* Custom prompt — consumed as `custom_instructions` by
                  /api/generate and /api/render-from-yaml. */}
              <div className="border-t-2 border-gray-300 pt-6">
                <label className="font-bold font-mono text-sm uppercase tracking-wide block mb-3">
                  ✍️ Instrucciones adicionales para la IA
                </label>
                <textarea
                  value={customPrompt}
                  onChange={(e) => onCustomPromptChange(e.target.value)}
                  placeholder="Ejemplo: Cambiar fecha Universidad Internacional de La Rioja (UNIR) Inicio: 2026-08 por 2026-08 - Actualidad..."
                  className="w-full border-2 border-black bg-white p-4 font-sans focus:outline-none focus:ring-4 focus:ring-blue-100 min-h-[100px] text-base placeholder-gray-400"
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default AdvancedOptions;