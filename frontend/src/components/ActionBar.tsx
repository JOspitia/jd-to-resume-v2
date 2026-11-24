import { motion } from 'framer-motion';
import { Play, Clock } from 'lucide-react';

import { Button } from './ui/Button';

/**
 * ActionBar — T7 of the UX refactor (specs S7, S8).
 *
 * Sticky bottom bar with ONE action: the primary "Generar CV" CTA. Full
 * width on mobile, centered with max-width on larger screens. The bar
 * itself is the only thing the user needs to see at the bottom — the
 * Translate / Audit / Reset actions live in the success card
 * (ResultsPanel) where they are contextually relevant.
 *
 * ToolApp adds `pb-32` (or similar) to the page container so the sticky
 * bar never covers the last form field.
 */

export type ActionBarProps = {
  status: 'idle' | 'generating' | 'success' | 'error';
  elapsedSeconds: number;
  hasFile: boolean;
  onGenerate: (customInstructionsOverride?: string, baseResumeFilename?: string, forceTranslate?: boolean) => void;
  /**
   * CTA copy. The bar serves two deliverables (the CV and the cover
   * letter), so the label follows the active one. Defaults keep the
   * original v2.5 wording for the CV flow.
   */
  ctaLabel?: string;
  ctaBusyLabel?: string;
  ctaEmptyLabel?: string;
  ctaAriaLabel?: string;
};

export function ActionBar({
  status,
  elapsedSeconds,
  hasFile,
  onGenerate,
  ctaLabel = 'Generar CV',
  ctaBusyLabel = 'Generando CV',
  ctaEmptyLabel = 'Subí un CV para empezar',
  ctaAriaLabel = 'Generar CV adaptado',
}: ActionBarProps) {
  const generating = status === 'generating';
  const disabled = generating || !hasFile;

  return (
    <div className="fixed bottom-0 inset-x-0 z-40 px-4 pb-4">
      <div className="max-w-3xl mx-auto">
        <Button
          onClick={() => onGenerate()}
          disabled={disabled}
          variant="primary"
          size="lg"
          aria-label={ctaAriaLabel}
          className="w-full px-8 py-5 text-lg md:text-xl justify-center font-extrabold tracking-tight"
        >
          {generating ? (
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
            >
              <Clock className="w-6 h-6" />
            </motion.div>
          ) : (
            <Play className="w-6 h-6 fill-current" />
          )}
          {generating
            ? `${ctaBusyLabel}… ${elapsedSeconds}s / 60s`
            : hasFile
              ? ctaLabel
              : ctaEmptyLabel}
        </Button>
      </div>
    </div>
  );
}

export default ActionBar;