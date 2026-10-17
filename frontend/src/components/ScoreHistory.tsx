import { motion } from 'framer-motion';
import type { ScoreEntry } from '../hooks/useAudit';

/**
 * ScoreHistory — T14 of the UX refactor (specs S4, S6).
 *
 * Timeline of the ATS score across refinement passes. Rendered at the bottom
 * of the results card once there is more than one scored version.
 */

export type ScoreHistoryProps = {
  entries: ScoreEntry[];
};

export function ScoreHistory({ entries }: ScoreHistoryProps) {
  if (entries.length <= 1) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="rm-box p-6 bg-card border-2 border-border relative w-full"
    >
      <div className="absolute -top-4 -left-4 rm-tag bg-foreground text-background px-4 py-2 text-sm font-black">
        📈 EVOLUCIÓN DE SCORES
      </div>
      <div className="flex flex-wrap items-end gap-4 mt-2 pt-2">
        {entries.map((entry, i) => {
          const prev = entries[i - 1];
          const delta = prev ? entry.ats - prev.ats : null;
          return (
            <div
              key={i}
              className={`flex flex-col items-center gap-1 p-3 border-2 min-w-[90px] ${delta === null
                ? 'border-gray-400 bg-muted'
                : delta > 0
                  ? 'border-green-500 bg-green-50'
                  : delta < 0
                    ? 'border-red-400 bg-red-50'
                    : 'border-gray-400 bg-muted'}`}
            >
              <span className="font-mono text-xs text-muted-foreground font-bold">{entry.label}</span>
              <span
                className={`text-3xl font-black font-mono ${entry.ats >= 75 ? 'text-green-600' : entry.ats >= 55 ? 'text-warning' : 'text-red-600'}`}
              >
                {entry.ats} %
              </span>
              {delta !== null && (
                <span className={`text-xs font-bold ${delta > 0 ? 'text-green-600' : delta < 0 ? 'text-red-500' : 'text-muted-foreground'}`}>
                  {delta > 0 ? `▲ +${delta}%` : delta < 0 ? `▼ ${delta}%` : '— sin cambio'}
                </span>
              )}
              <span className="text-xs text-muted-foreground font-mono">ATS Match</span>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}

export default ScoreHistory;