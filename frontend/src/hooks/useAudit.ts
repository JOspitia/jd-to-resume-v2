import { useRef, useState } from 'react';
import type { Profile } from './useProfile';

/**
 * useAudit — T4 of the UX refactor (spec S6).
 *
 * Owns the ATS / AI-detection audit surface: the `/api/analyze-ats` request,
 * the `/api/analyze-yaml` score push, the score history timeline and the
 * user selections (keywords + humanization tips) that are later compiled into
 * the regeneration prompt.
 */

export type AuditStatus = 'idle' | 'analyzing' | 'success' | 'error';

/** Score history — tracks ATS evolution across regeneration versions. */
export type ScoreEntry = { version: number; ats: number; ai: number; format: number; label: string };

export type ScoreSample = {
  ats: number;
  ai: number;
  format: number;
  /** Forced-translation passes are labelled 'EN' instead of 'Refinado vN'. */
  forced?: boolean;
  /** Overrides the derived label (used by the YAML audit flow). */
  label?: string;
};

export function useAudit(
  profile: Pick<Profile, 'file' | 'jd' | 'domainGame'>,
  /**
   * `useAudit` is created before `useGeneration` (which owns `status` /
   * `errorMessage`), yet the "no file selected" path has always surfaced the
   * failure in the generation status area. ToolApp wires this bridge so the
   * message and the status transition stay byte-identical.
   */
  onMissingFile: () => void,
) {
  const { file, jd, domainGame } = profile;

  const [atsStatus, setAtsStatus] = useState<AuditStatus>('idle');
  const [atsData, setAtsData] = useState<any | null>(null);
  const [atsErrorMessage, setAtsErrorMessage] = useState('');

  // Score history — tracks ATS evolution across regeneration versions
  const [scoreHistory, setScoreHistory] = useState<ScoreEntry[]>([]);
  const generationVersionRef = useRef(0);

  // Refinement states: the user picks missing keywords and AI-humanization /
  // actionable tips; `handleRegenerateWithFeedback` (useGeneration) compiles
  // them into the custom instructions of the next /api/generate pass.
  const [selectedTips, setSelectedTips] = useState<string[]>([]);
  const [selectedKeywords, setSelectedKeywords] = useState<string[]>([]);

  const toggleTip = (tip: string) => {
    setSelectedTips(prev =>
      prev.includes(tip) ? prev.filter(t => t !== tip) : [...prev, tip]
    );
  };

  const toggleKeyword = (kw: string) => {
    setSelectedKeywords(prev =>
      prev.includes(kw) ? prev.filter(k => k !== kw) : [...prev, kw]
    );
  };

  /**
   * Appends one point to the score timeline and bumps the generation counter.
   * The counter is shared with `useGeneration` (SSE audit_scores branch) and
   * with `useYamlEditor` (which bumps it when re-rendering from YAML without
   * producing a new ATS score of its own).
   */
  const recordScore = (sample: ScoreSample) => {
    generationVersionRef.current += 1;
    const version = generationVersionRef.current;
    const label = sample.label ?? (sample.forced ? 'EN' : version === 1 ? 'Original' : `Refinado v${version - 1}`);
    setScoreHistory(prev => [
      ...prev,
      { version, ats: sample.ats, ai: sample.ai, format: sample.format, label },
    ]);
  };

  const resetAudit = () => {
    setAtsStatus('idle');
    setAtsData(null);
    setAtsErrorMessage('');
    setScoreHistory([]);
    setSelectedTips([]);
    setSelectedKeywords([]);
    generationVersionRef.current = 0;
  };

  const handleValidateATS = async (overrideFile?: File | null) => {
    // overrideFile is used by the audit-after-render flow (T8 of yaml-editor
    // feature) which audits the freshly rendered PDF instead of the original
    // upload. Falls back to the uploaded `file` state for the standalone
    // SOLO AUDITAR ATS button.
    const fileToAudit = overrideFile ?? file;
    if (!fileToAudit) {
      onMissingFile();
      return;
    }

    setAtsStatus('analyzing');
    setAtsErrorMessage('');

    const formData = new FormData();
    formData.append("file", fileToAudit);
    formData.append("jd", jd);
    // T6 of multi-domain: propagate the active profile so the backend builds
    // the audit prompt with the right SKILL_TAXONOMY (hr_recruiting /
    // psychology / tech). Without this, /api/analyze-ats falls back to the
    // "tech" game and the LLM audits the HR CV against tech keywords.
    if (domainGame) formData.append("domain_game", domainGame);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second (1 minute) timeout

    try {
      const res = await fetch("http://localhost:8000/api/analyze-ats", {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!res.ok) {
        throw new Error("No se pudo conectar con el servidor de análisis.");
      }

      const data = await res.json();
      if (data.error) {
        setAtsErrorMessage(data.error);
        setAtsStatus('error');
      } else {
        setAtsData(data);
        setAtsStatus('success');
        // Track score history for this audit pass
        recordScore({
          ats: data.ats_score ?? 0,
          ai: data.ai_detection_score ?? 0,
          format: data.ats_formatting_score ?? 0,
        });
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        setAtsErrorMessage("La solicitud de análisis ATS agotó el tiempo de espera (1 min). Por favor reintenta.");
      } else {
        setAtsErrorMessage(err.message || "Ocurrió un error inesperado al analizar el ATS.");
      }
      setAtsStatus('error');
    }
  };

  return {
    atsStatus,
    setAtsStatus,
    atsData,
    setAtsData,
    atsErrorMessage,
    setAtsErrorMessage,
    handleValidateATS,
    scoreHistory,
    generationVersionRef,
    recordScore,
    resetAudit,
    selectedTips,
    selectedKeywords,
    toggleTip,
    toggleKeyword,
  };
}

export type Audit = ReturnType<typeof useAudit>;