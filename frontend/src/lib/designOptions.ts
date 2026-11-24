/**
 * Design options — templates and accent palettes.
 *
 * The backend is the source of truth (`GET /api/design-options`): the swatch
 * a user clicks must show the exact hex the renderer will apply, otherwise
 * the UI and the PDF drift apart. The static lists below are only a fallback
 * for the first paint (and for when the request fails) — the same approach
 * the template picker already uses.
 *
 * The catalogue is fetched once per page load and shared by every consumer
 * (the advanced-options picker and the redesign panel), so opening the
 * redesign panel does not trigger a second request.
 */

import { useEffect, useState } from 'react';
import { apiUrl } from './api';

export type ThemeOption = {
  id: string;
  name: string;
  badge: string;
  description: string;
};

export type PaletteOption = {
  id: string;
  label: string;
  hex: string;
  description: string;
};

/** The cover-letter layouts the backend can render. */
export type LetterStyleOption = {
  id: string;
  name: string;
  badge: string;
  description: string;
};

/** Mirrors `backend/routes/design_router.py`. */
export const THEMES: ThemeOption[] = [
  { id: 'sb2nov', name: 'SB2Nov', badge: 'ATS / Silicon Valley', description: 'Limpio y estructurado para Tech' },
  { id: 'classic', name: 'Classic', badge: 'Sobrio', description: 'Tradicional, elegante y universal' },
  { id: 'moderncv', name: 'ModernCV', badge: 'Visual', description: 'Detalles a color y tipografía moderna' },
  { id: 'classic_html', name: 'Classic HTML', badge: 'Playwright', description: 'Renderizado web tradicional' },
];

/** Fallback palette list, used while the catalogue request is in flight. */
export const FALLBACK_PALETTES: PaletteOption[] = [
  { id: 'none', label: 'Sin color', hex: '#000000', description: 'Negro y blanco, el más seguro para ATS' },
  { id: 'navy', label: 'Azul marino', hex: '#1B3A5C', description: 'Color de acento en nombre y títulos' },
  { id: 'teal', label: 'Verde azulado', hex: '#0F5C57', description: 'Color de acento en nombre y títulos' },
  { id: 'forest', label: 'Verde bosque', hex: '#23543B', description: 'Color de acento en nombre y títulos' },
  { id: 'burgundy', label: 'Granate', hex: '#6E2639', description: 'Color de acento en nombre y títulos' },
  { id: 'plum', label: 'Ciruela', hex: '#5B2D63', description: 'Color de acento en nombre y títulos' },
  { id: 'slate', label: 'Gris pizarra', hex: '#3D4A5C', description: 'Color de acento en nombre y títulos' },
];

/** Fallback letter styles, used while the catalogue request is in flight. */
export const FALLBACK_LETTER_STYLES: LetterStyleOption[] = [
  { id: 'classic', name: 'Clásica', badge: 'Sobrio', description: 'Encabezado centrado y cuerpo serif.' },
  { id: 'modern', name: 'Moderna', badge: 'Limpia', description: 'Encabezado a la izquierda y sin serifas.' },
  { id: 'sidebar', name: 'Lateral', badge: 'Visual', description: 'Contactos a la izquierda, carta a la derecha.' },
];

type Catalogue = {
  themes: ThemeOption[];
  palettes: PaletteOption[];
  letterStyles: LetterStyleOption[];
};

let cataloguePromise: Promise<Catalogue> | null = null;

/** Fetch the catalogue once; subsequent calls reuse the same request. */
function loadCatalogue(): Promise<Catalogue> {
  if (!cataloguePromise) {
    cataloguePromise = fetch(apiUrl('/api/design-options'))
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error('HTTP ' + res.status))))
      .then((data) => ({
        themes: Array.isArray(data?.themes) && data.themes.length > 0 ? data.themes : THEMES,
        palettes:
          Array.isArray(data?.palettes) && data.palettes.length > 0 ? data.palettes : FALLBACK_PALETTES,
        letterStyles:
          Array.isArray(data?.letter_styles) && data.letter_styles.length > 0
            ? data.letter_styles
            : FALLBACK_LETTER_STYLES,
      }))
      .catch(() => {
        // Allow a later retry (e.g. the backend was still booting).
        cataloguePromise = null;
        return {
          themes: THEMES,
          palettes: FALLBACK_PALETTES,
          letterStyles: FALLBACK_LETTER_STYLES,
        };
      });
  }
  return cataloguePromise;
}

/**
 * React hook exposing the design catalogue.
 *
 * Renders the static fallback immediately (so the picker is never empty)
 * and swaps in the backend catalogue once it arrives.
 */
export function useDesignOptions(): Catalogue {
  const [catalogue, setCatalogue] = useState<Catalogue>({
    themes: THEMES,
    palettes: FALLBACK_PALETTES,
    letterStyles: FALLBACK_LETTER_STYLES,
  });

  useEffect(() => {
    let cancelled = false;
    loadCatalogue().then((loaded) => {
      if (!cancelled) setCatalogue(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return catalogue;
}
