import { AnimatePresence, motion } from 'framer-motion';
import { Clock, AlertCircle } from 'lucide-react';

/**
 * GenerationProgress — T10 of the UX refactor (specs S4, S6).
 *
 * Live progress surface of the `/api/generate` pipeline: the SSE step message,
 * the percentage bar, the elapsed-seconds counter (shared with the ATS audit)
 * and the failure state.
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
          className={`rm-box p-10 mt-8 mx-auto max-w-3xl transform rotate-1 ${status === 'generating' ? 'bg-white' : 'bg-[#fef2f2]'}`}
        >
          {status === 'generating' && (
            <div className="space-y-6">
              <div className="flex justify-between items-end border-b-2 border-black pb-4">
                <div>
                  <h3 className="text-2xl font-bold font-serif">{stepMessage}</h3>
                  <div className="flex items-center gap-2 mt-1 text-sm font-mono font-bold text-blue-800">
                    <Clock className="w-4 h-4 animate-spin text-blue-600" />
                    <span>Tiempo transcurrido: {elapsedSeconds} s / 60s</span>
                  </div>
                </div>
                <span className="text-3xl font-black font-mono">{progress} %</span>
              </div>
              <div className="w-full border-2 border-black h-10 bg-gray-100 overflow-hidden relative">
                <div
                  className="bg-blue-700 h-full transition-all duration-300 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {status === 'error' && (
            <div className="flex flex-col md:flex-row items-center gap-6 text-red-700">
              <AlertCircle className="w-16 h-16 shrink-0" />
              <div>
                <h3 className="text-2xl font-bold font-serif mb-2">Process Failed</h3>
                <p className="font-semibold text-lg text-black">{errorMessage}</p>
              </div>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default GenerationProgress;