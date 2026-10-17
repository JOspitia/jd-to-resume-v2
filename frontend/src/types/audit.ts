/**
 * Shared types for the audit pipeline.
 *
 * Lives in `src/types/` so it can be imported from both
 * ``useAudit`` (state owner) and ``useGeneration`` (which also
 * stores a snapshot in ``auditScores``) without the two
 * ``any | null`` declarations drifting apart. The backend shape
 * is exhaustively described here; if a new field is added to
 * the /api/analyze-ats response, extend this interface and the
 * TypeScript compiler will surface every consumer that needs
 * to react.
 */

export interface AuditData {
  /** ATS compatibility score 0-100, as judged by the auditor. */
  ats_score?: number;
  /** AI-detection score 0-100; high means the text looks AI-generated. */
  ai_detection_score?: number;
  /** Free-form verdict tied to ``ai_detection_score`` (e.g. "Bajo Riesgo de IA"). */
  ai_tone_verdict?: string;
  /** Match level label ("Alto" / "Medio" / "Bajo" …) shown as a pill. */
  match_level?: string;
  /** Layout / formatting pass score 0-100 from the audit pipeline. */
  ats_formatting_score?: number;
  /** Keywords already present in the CV. */
  matched_keywords?: string[];
  /** Keywords the JD asks for but the CV lacks. */
  missing_keywords?: string[];
  /** Tip strings surfaced to the user to humanize AI-detected text. */
  ai_humanize_tips?: string[];
  /** Concrete actionable suggestions to raise the ATS score. */
  actionable_tips?: string[];
}
