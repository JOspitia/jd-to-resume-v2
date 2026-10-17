import { AnimatePresence, motion } from 'framer-motion';
import { Clock, AlertCircle } from 'lucide-react';

/**
 * GenerationProgress — T10 of the UX refactor (specs S4, S6).
 *
 * Live progress surface of the `/api/generate` pipeline: the SSE step message,
 * the percentage bar, the elapsed-seconds counter (shared with the ATS audit)
 * and the failure state.
 *
 * Accessibility (PR3):
 *   - `role="status" aria-live="polite" aria-atomic="true"` on the wrapper so
 *     screen readers announce step changes without interrupting the user.
 *   - `role="progressbar"` on the bar with aria-valuemin/max/now + aria-label
 *     so assistive tech reads the percent out and the user knows what it is.
 *   - `aria-busy="true"` while generating (visually the rotating icon
 *     signals activity; ARIA signals it semantically).
 *   - Error state gets `role="alert"` so screen readers announce it
 *     immediately (errors should interrupt).
 */

export type GenerationProgressProps = {
  status: 'idle' | 'generating' | 'success' | 'error';
  progress: number;
  stepMessage: string;
  elapsedSeconds: number;
  errorMessage: string;
};

export function GenerationProgress({
  status,
  progress,
  stepMessage,
  elapsedSeconds,
  errorMessage,
}: GenerationProgressProps) {
  return (
    <AnimatePresence mode="popLayout">
      {status !== 'idle' && status !== 'success' && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95 }}
          className={`rm-box p-10 mt-8 mx-auto max-w-3xl transform rotate-1 ${status === 'generating' ? 'bg-card' : 'bg-destructive/10'}`}
          role={status === 'error' ? 'alert' : 'status'}
          aria-live={status === 'error' ? 'assertive' : 'polite'}
          aria-atomic="true"
        >
          {status === 'generating' && (
            <div className="space-y-6" aria-busy="true">
              <div className="flex justify-between items-end border-b-2 border-border pb-4">
                <div>
                  <h3 className="text-2xl font-bold font-serif">{stepMessage}</h3>
                  <div className="flex items-center gap-2 mt-1 text-sm font-mono font-bold text-primary">
                    <Clock className="w-4 h-4 animate-spin text-primary" aria-hidden="true" />
                    <span>Tiempo transcurrido: {elapsedSeconds} s / 60s</span>
                  </div>
                </div>
                <span className="text-3xl font-black font-mono" aria-hidden="true">{progress} %</span>
              </div>
              <div
                className="w-full border-2 border-border h-10 bg-muted overflow-hidden relative"
                role="progressbar"
                aria-label="Progreso de generación del CV"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progress}
              >
                <div
                  className="bg-primary h-full transition-all duration-300 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {status === 'error' && (
            <div className="flex flex-col md:flex-row items-center gap-6 text-red-700">
              <AlertCircle className="w-16 h-16 shrink-0" aria-hidden="true" />
              <div>
                <h3 className="text-2xl font-bold font-serif mb-2">Process Failed</h3>
                <p className="font-semibold text-lg text-foreground">{errorMessage}</p>
              </div>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default GenerationProgress;