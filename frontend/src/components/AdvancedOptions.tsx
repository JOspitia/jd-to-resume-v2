import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown, SlidersHorizontal, Palette, LayoutTemplate,
  FileCheck2, PenLine, MessageSquare } from 'lucide-react';

/**
 * AdvancedOptions — T3 of the UX refactor (specs S3, S4).
 *
 * Collapsible container for the ~80% of users who never touch theme,
 * page-break, auto ATS, edit-YAML, strict-edits, custom-prompt.
 *
 * The header is intentionally clickable with a large aria-expanded
 * chevron so the collapse is obvious. First visit opens the panel
 * (so the user can see what's there once); after that the choice
 * is remembered in localStorage.
 *
 * Wrapped by <Section number={4} title="OPCIONES AVANZADAS"> in ToolApp.
 *
 * NOTE: implemented with a native button + framer-motion because the
 * project ships no @radix-ui/react-collapsible and this refactor adds
 * no dependencies.
 */

const STORAGE_KEY = 'jd-to-resume.advanced-options';

const THEMES = [
  { id: 'sb2nov', name: 'SB2Nov', badge: 'ATS / Silicon Valley', desc: 'Limpio y estructurado para Tech' },
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
  // Open on the very first visit; afterwards honour the user's choice.
  // Deliberately NOT cleared by "Nuevo / Limpiar".
  const [open, setOpen] = useState<boolean>(() => {
    try {
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
    <div className="space-y-5">
      {/* Theme selector — always visible, this is the #1 most-tweaked option. */}
      <fieldset>
        <legend className="font-bold font-mono text-xs uppercase tracking-wide text-gray-700 flex items-center gap-1.5 mb-2">
          <Palette className="w-3.5 h-3.5" /> Plantilla
        </legend>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {THEMES.map((t) => {
            const selected = selectedTheme === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => onThemeChange(t.id)}
                aria-pressed={selected}
                className={`p-2.5 text-left border-2 transition-all ${
                  selected
                    ? 'border-blue-700 bg-blue-50 font-bold shadow-[2px_2px_0px_0px_rgba(29,78,216,1)]'
                    : 'border-black bg-white hover:bg-gray-50'
                }`}
              >
                <span className="text-[10px] font-mono px-1 py-0.5 bg-gray-200 text-black font-bold uppercase inline-block mb-1">
                  {t.badge}
                </span>
                <div className="text-xs font-serif font-bold text-black">{t.name}</div>
                <div className="text-[10px] text-gray-600 mt-0.5 leading-tight">{t.desc}</div>
              </button>
            );
          })}
        </div>
      </fieldset>

      {/* Collapsible: page break + auto ATS + edit YAML + strict + custom prompt */}
      <div>
        <button
          type="button"
          onClick={toggleOpen}
          aria-expanded={open}
          aria-controls="advanced-collapsible-body"
          className="w-full flex items-center justify-between gap-4 text-left cursor-pointer select-none py-2 px-3 border-2 border-black bg-white hover:bg-gray-50 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
        >
          <span className="flex items-center gap-2 text-sm font-bold font-mono uppercase tracking-wide">
            <SlidersHorizontal className="w-4 h-4" /> Más opciones
          </span>
          <span className="flex items-center gap-2 font-mono text-xs uppercase text-gray-600">
            {open ? 'Ocultar' : 'Mostrar'}
            <motion.span
              animate={{ rotate: open ? 180 : 0 }}
              transition={{ duration: 0.2 }}
            >
              <ChevronDown className="w-4 h-4" />
            </motion.span>
          </span>
        </button>

        <AnimatePresence initial={false}>
          {open && (
            <motion.div
              id="advanced-collapsible-body"
              key="advanced-options"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: 'easeInOut' }}
              className="overflow-hidden"
            >
              <div className="pt-4 space-y-4">
                {/* Page break control */}
                <div className="flex items-start gap-3 bg-white border-2 border-black p-3 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                  <LayoutTemplate className="w-4 h-4 mt-1 shrink-0" />
                  <div className="flex-1">
                    <div className="font-bold text-sm">Insertar salto de página antes de:</div>
                    <div className="text-xs text-gray-600 mb-1.5">
                      Para CVs de 2 hojas: divide una sección completa al inicio de la página 2.
                    </div>
                    <select
                      value={pageBreakSection}
                      onChange={(e) => onPageBreakSectionChange(e.target.value)}
                      className="w-full border-2 border-black bg-white p-1.5 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-blue-600"
                    >
                      <option value="none">Sin salto manual (auto anti-huérfanas)</option>
                      <option value="Experience">Experiencia Laboral</option>
                      <option value="Education">Educación</option>
                      <option value="Projects">Proyectos</option>
                      <option value="Skills">Habilidades</option>
                      <option value="Achievements">Logros</option>
                    </select>
                  </div>
                </div>

                {/* Compact: fit-single-page toggle + auto-audit toggle in a 2-col row */}
                <div className="grid sm:grid-cols-2 gap-2">
                  <label className="flex items-start gap-2 bg-white border-2 border-black p-3 cursor-pointer hover:bg-gray-50 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] select-none">
                    <input
                      type="checkbox"
                      checked={fitSinglePage}
                      onChange={(e) => onFitSinglePageChange(e.target.checked)}
                      className="w-4 h-4 mt-0.5 accent-blue-700 cursor-pointer"
                    />
                    <div>
                      <div className="font-bold text-xs">Ajuste compacto (1 página)</div>
                      <div className="text-[10px] text-gray-600 leading-tight">
                        Reduce márgenes/interlineado para evitar desbordes.
                      </div>
                    </div>
                  </label>

                  <label className="flex items-start gap-2 bg-white border-2 border-black p-3 cursor-pointer hover:bg-gray-50 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] select-none">
                    <input
                      type="checkbox"
                      checked={autoValidateATS}
                      onChange={(e) => onAutoValidateAtsChange(e.target.checked)}
                      className="w-4 h-4 mt-0.5 accent-blue-700 cursor-pointer"
                    />
                    <div>
                      <div className="font-bold text-xs">Auto-validar ATS al terminar</div>
                      <div className="text-[10px] text-gray-600 leading-tight">
                        Corre el audit del CV en cuanto se renderiza.
                      </div>
                    </div>
                  </label>
                </div>

                {/* Edit YAML */}
                <label className="flex items-start gap-3 bg-white border-2 border-black p-3 font-mono cursor-pointer hover:bg-gray-50 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] select-none">
                  <input
                    type="checkbox"
                    checked={editBeforeGenerate}
                    onChange={(e) => onEditBeforeGenerateChange(e.target.checked)}
                    className="w-4 h-4 mt-0.5 accent-blue-700 cursor-pointer shrink-0"
                  />
                  <div>
                    <div className="font-bold text-xs flex items-center gap-1.5">
                      <FileCheck2 className="w-3.5 h-3.5" /> Editar YAML antes de generar
                    </div>
                    <div className="text-[10px] text-gray-600 leading-tight">
                      Para hacer ajustes manuales antes de renderizar el PDF.
                    </div>
                  </div>
                </label>

                {/* Strict surgical edit toggle */}
                <label className="flex items-start gap-3 bg-yellow-50 border-2 border-black p-3 cursor-pointer hover:bg-yellow-100 transition-all select-none shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]">
                  <input
                    type="checkbox"
                    checked={strictEditsOnly}
                    onChange={(e) => onStrictEditsOnlyChange(e.target.checked)}
                    className="w-4 h-4 mt-0.5 accent-yellow-600 cursor-pointer shrink-0"
                  />
                  <div>
                    <div className="font-bold text-xs flex items-center gap-1.5">
                      <PenLine className="w-3.5 h-3.5" /> Modo SOLO cambios solicitados
                    </div>
                    <div className="text-[10px] text-gray-700 leading-tight">
                      Ajustes puntuales sin reescribir nada más.
                    </div>
                  </div>
                </label>

                {/* Custom prompt */}
                <div className="border-t-2 border-gray-200 pt-3">
                  <label
                    htmlFor="custom-prompt"
                    className="font-bold font-mono text-xs uppercase tracking-wide text-gray-700 flex items-center gap-1.5 mb-1.5"
                  >
                    <MessageSquare className="w-3.5 h-3.5" /> Instrucciones adicionales para la IA
                  </label>
                  <textarea
                    id="custom-prompt"
                    value={customPrompt}
                    onChange={(e) => onCustomPromptChange(e.target.value)}
                    placeholder="Ej: Cambiar fecha UNIR 2026-08 por 2026-08 - Actualidad..."
                    className="w-full border-2 border-black bg-white p-2.5 font-sans text-sm focus:outline-none focus:ring-4 focus:ring-blue-100 min-h-[80px] placeholder-gray-400"
                  />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

export default AdvancedOptions;
