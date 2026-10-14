import { useEffect, useState } from 'react';
import type { RefObject } from 'react';
import type { Profile } from './useProfile';
import type { Audit } from './useAudit';
import type { YamlEditorOps } from './useYamlEditor';

/**
 * useGeneration — T2 of the UX refactor (specs S1, S4, S6).
 *
 * Owns the `/api/generate` pipeline: request FormData, the SSE reader loop,
 * the abort/timeout logic, the progress + step-message surface and the
 * translation / audit bookkeeping that arrives on the same SSE event.
 */

export type GenerationStatus = 'idle' | 'generating' | 'success' | 'error';
export type OutputLanguage = 'en' | 'es' | 'unknown';

type GenerationDeps = {
  profile: Pick<
    Profile,
    | 'file'
    | 'jd'
    | 'targetRole'
    | 'githubUrl'
    | 'linkedinUrl'
    | 'portfolioUrl'
    | 'domainGame'
    | 'extractLinkedinInfo'
    | 'step2Mode'
    | 'customPrompt'
    | 'strictEditsOnly'
    | 'selectedTheme'
    | 'fitSinglePage'
    | 'pageBreakSection'
    | 'editBeforeGenerate'
    | 'autoValidateATS'
    | 'photo'
  >;
  audit: Audit;
  /**
   * Late-bound handle to the YAML editor panel. `/api/generate` streams the
   * `yaml_ready` event, so the SSE reader has to open the editor panel that
   * lives in `useYamlEditor` — which in turn calls `handleGenerate`. ToolApp
   * fills this ref right after creating the editor hook; the reader only
   * dereferences it at event time, long after the cycle is resolved.
   */
  yamlOpsRef: RefObject<YamlEditorOps | null>;
};

export function useGeneration({ profile, audit, yamlOpsRef }: GenerationDeps) {
  const {
    file,
    jd,
    targetRole,
    githubUrl,
    linkedinUrl,
    portfolioUrl,
    domainGame,
    extractLinkedinInfo,
    step2Mode,
    customPrompt,
    strictEditsOnly,
    selectedTheme,
    fitSinglePage,
    pageBreakSection,
    editBeforeGenerate,
    autoValidateATS,
    photo,
  } = profile;

  const [status, setStatus] = useState<GenerationStatus>('idle');
  const [progress, setProgress] = useState(0);
  const [stepMessage, setStepMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [downloadUrl, setDownloadUrl] = useState('');
  const [generatedPdfFilename, setGeneratedPdfFilename] = useState<string | null>(null);

  // Translation state — populated by the SSE handler after each generation/translate pass.
  // `forceTranslateToEnglish` is set on click and reset in handleGenerate's finally block.
  const [forceTranslateToEnglish, setForceTranslateToEnglish] = useState<boolean>(false);
  const [lastOutputLanguage, setLastOutputLanguage] = useState<OutputLanguage>('unknown');
  const [auditScores, setAuditScores] = useState<{
    ats_score?: number;
    ai_detection_score?: number;
    match_level?: string;
    ai_tone_verdict?: string;
    ats_formatting_score?: number;
    matched_keywords?: string[];
    missing_keywords?: string[];
  } | null>(null);
  const [translationMeta, setTranslationMeta] = useState<{
    source_language?: string;
    target_language?: string;
    forced?: boolean;
  } | null>(null);

  // Snapshot of the YAML that produced the currently-displayed PDF. Set on a
  // successful `handleRenderFromYaml` and on the direct (non-edit) SSE pass.
  // Used by `handleReopenYamlEditor` (useYamlEditor) so the user can re-open
  // the editor after the CV is generated and iterate (edit → re-render →
  // open again → re-edit). Independent of `yamlContent`, which represents the
  // live textarea state and gets cleared on success.
  const [lastGeneratedYaml, setLastGeneratedYaml] = useState<string | null>(null);

  // Live timer for loading states (seconds counter up to 60s)
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    let interval: any = null;
    if (status === 'generating' || audit.atsStatus === 'analyzing') {
      interval = setInterval(() => {
        setElapsedSeconds(prev => prev + 1);
      }, 1000);
    } else {
      setElapsedSeconds(0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [status, audit.atsStatus]);

  /** Resets the generation surface (mirrors the pre-refactor reset handler). */
  const resetGeneration = () => {
    setStatus('idle');
    setProgress(0);
    setStepMessage('');
    setErrorMessage('');
    setDownloadUrl('');
    setGeneratedPdfFilename(null);
    setForceTranslateToEnglish(false);
    setLastOutputLanguage('unknown');
    setAuditScores(null);
    setTranslationMeta(null);
  };

  const handleGenerate = async (customInstructionsOverride?: string, baseResumeFilename?: string, forceTranslate?: boolean) => {
    if (!file) {
      setErrorMessage("Please select a resume PDF to upload.");
      setStatus('error');
      return;
    }

    setStatus('generating');
    setProgress(0);
    setStepMessage('Starting process...');
    setErrorMessage('');
    // Reset the generated filename only on a brand-new generation (not refinement)
    if (!baseResumeFilename) {
      setGeneratedPdfFilename(null);
    }

    // Sync the state flag from the explicit parameter so the rest of this function
    // reads the correct value (avoids the React useState closure race).
    if (forceTranslate !== undefined) {
      setForceTranslateToEnglish(forceTranslate);
    }

    // Create form data
    const formData = new FormData();
    formData.append("file", file);
    if (step2Mode === 'custom' && !customInstructionsOverride) {
      formData.append("custom_instructions", jd);
      formData.append("jd", "");
    } else {
      formData.append("jd", jd);
      if (customInstructionsOverride) {
        formData.append("custom_instructions", customInstructionsOverride);
      }
    }
    if (targetRole) formData.append("target_role", targetRole);
    if (githubUrl) formData.append("github_url", githubUrl);
    if (linkedinUrl) formData.append("linkedin_url", linkedinUrl);
    if (portfolioUrl) formData.append("portfolio_url", portfolioUrl);
    // Only extract LinkedIn info on first generation — not on refinement passes (no need to re-scrape)
    const shouldExtractLinkedin = extractLinkedinInfo && !baseResumeFilename;
    formData.append("extract_linkedin_info", shouldExtractLinkedin ? "true" : "false");
    formData.append("strict_edits_only", strictEditsOnly ? "true" : "false");
    formData.append("theme", selectedTheme);
    formData.append("fit_single_page", fitSinglePage ? "true" : "false");
    // Multi-domain selection (feat/multi-domain-tailoring).
    // The backend uses this to compose the prompt body via domain_games.get_game().
    formData.append("domain_game", domainGame);
    // Edit-before-generate flag (feat/yaml-editor). When true, the backend
    // stops after the LLM call and streams the parsed_data as YAML over SSE
    // (the `yaml_ready` event) instead of rendering a PDF.
    formData.append("edit_before_generate", editBeforeGenerate ? "true" : "false");
    // Optional candidate photo. Re-sent on refinement passes too, so changing
    // the photo alone still reproduces the whole CV without a fresh upload.
    if (photo) formData.append("photo", photo);
    if (pageBreakSection && pageBreakSection !== 'none') {
      formData.append("page_break_section", pageBreakSection);
    }
    // Pass the previously generated PDF filename so the backend refines it instead of starting fresh

    if (baseResumeFilename) {
      formData.append("base_resume_filename", baseResumeFilename);
    }

    // Translation flag — only true on the click that initiates translation.
    // Use the local `forceTranslate` parameter (or the state) to decide.
    // Cleared in the finally block so subsequent refinements do not accidentally re-translate.
    const shouldTranslate = forceTranslate !== undefined ? forceTranslate : forceTranslateToEnglish;
    if (shouldTranslate) {
      formData.append("force_language", "en");
      // Translate the LAST-GENERATED PDF (preserves iterative tailoring decisions).
      // If no PDF has been generated yet, backend falls back to the original upload.
      if (generatedPdfFilename) {
        formData.append("base_resume_filename", generatedPdfFilename);
      }
    }

    try {
      const response = await fetch("http://localhost:8000/api/generate", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to connect to backend api.");
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (let line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const dataStr = line.replace('data: ', '').trim();
                if (!dataStr) continue;
                const data = JSON.parse(dataStr);

                if (data.error) {
                  setErrorMessage(data.error);
                  setStatus('error');
                  return;
                }

                if (data.step) setStepMessage(data.step);
                if (data.progress) setProgress(data.progress);

                // === YAML editor (feat/yaml-editor) ===
                // The backend emitted a `yaml_ready` event: the LLM has
                // produced parsed_data and the user wants to edit the
                // YAML before rendering. Stash the YAML and open the
                // editor panel (rendered in T7).
                if (data.yaml_ready && typeof data.yaml === 'string') {
                  yamlOpsRef.current?.open(data.yaml);
                  setStatus('idle');
                  setProgress(100);
                  setStepMessage(data.step || 'YAML listo para revisión');
                  return;
                }

                if (data.download_url) {
                  const fullUrl = `http://localhost:8000${data.download_url}`;
                  setDownloadUrl(fullUrl);
                  // Extract and store just the filename for future refinement passes
                  const filename = data.download_url.split('/').pop() || null;
                  setGeneratedPdfFilename(filename);
                  setStatus('success');

                  // Translation meta + audit scores arrive on the same SSE event
                  // when force_language='en' triggered the translation path (REQ-4).
                  if (data.translation) {
                    setTranslationMeta(data.translation);
                    const srcLang = (data.translation.source_language as OutputLanguage) || 'unknown';
                    const tgtLang = (data.translation.target_language as 'en' | 'es') || 'es';
                    setLastOutputLanguage(srcLang === 'en' ? 'en' : tgtLang);
                  } else if (forceTranslateToEnglish) {
                    // Defensive fallback: backend didn't echo translation meta
                    // but the click that just succeeded was a translation pass.
                    setLastOutputLanguage('en');
                  } else if (lastOutputLanguage === 'unknown') {
                    // Default user base assumption: original CVs are Spanish.
                    setLastOutputLanguage('es');
                  }

                  if (data.audit_scores) {
                    setAuditScores(data.audit_scores);
                    audit.setAtsData(data.audit_scores);
                    audit.setAtsStatus('success');
                    audit.recordScore({
                      ats: data.audit_scores.ats_score ?? 0,
                      ai: data.audit_scores.ai_detection_score ?? 0,
                      format: data.audit_scores.ats_formatting_score ?? 95,
                      forced: data.translation?.forced,
                    });
                  }

                  // Snapshot the YAML that produced this PDF so the user can
                  // re-open the editor after a non-edit-before-generate pass.
                  // The backend emits `data.yaml` on the Finished event for
                  // the direct path; the edit_before_generate path returns
                  // earlier with its own yaml_ready event and snapshots there.
                  if (typeof data.yaml === 'string' && data.yaml) {
                    setLastGeneratedYaml(data.yaml);
                  }

                  // Auto re-audit: always re-audit on refinement passes; on first gen only if checkbox enabled
                  if (autoValidateATS || baseResumeFilename) {
                    audit.handleValidateATS();
                  }
                }
              } catch (e) {
                console.error("Error parsing SSE:", e, line);
              }
            }
          }
        }
      }
    } catch (err: any) {
      setErrorMessage(err.message || "An unexpected error occurred.");
      setStatus('error');
    } finally {
      // Always clear the translation flag so the next generation reverts to JD-driven
      // language unless the user explicitly clicks Translate to English again.
      if (shouldTranslate) {
        setForceTranslateToEnglish(false);
      }
    }
  };

  /**
   * Compiles the audit selections (ATS keyword constraints, humanization
   * tips, custom prompt) into a single `custom_instructions` payload and
   * refines the *last generated* PDF instead of the original upload.
   */
  const handleRegenerateWithFeedback = () => {
    const compiledParts: string[] = [];

    // CRITICAL: Inject ATS keyword constraints first so they are never sacrificed
    // when applying humanization tips or custom instructions
    if (audit.atsData) {
      const keywordConstraints: string[] = [];

      // Include current score + target so the AI knows exactly what benchmark to beat
      if (typeof audit.atsData.ats_score === 'number') {
        const targetScore = Math.min(audit.atsData.ats_score + 20, 90);
        keywordConstraints.push(
          `SCORE ATS ACTUAL DEL CV: ${audit.atsData.ats_score}%. OBJETIVO MÍNIMO A SUPERAR: ${targetScore}%. Debes mejorar la densidad y relevancia de keywords para alcanzar o superar ese umbral.`
        );
      }

      if (audit.atsData.matched_keywords && audit.atsData.matched_keywords.length > 0) {
        keywordConstraints.push(
          `KEYWORDS ATS YA DETECTADAS — DEBES CONSERVAR TODAS (no elimines ninguna): ${audit.atsData.matched_keywords.join(', ')}.`
        );
      }

      if (audit.selectedKeywords.length > 0) {
        keywordConstraints.push(
          `PALABRAS CLAVE FALTANTES MARCADAS EXPLÍCITAMENTE POR EL USUARIO PARA INCORPORAR (MÁXIMA PRIORIDAD): ${audit.selectedKeywords.join(', ')}. Debes incorporarlas de manera fluida y profesional en las secciones de Habilidades (Skills) o en los bullet points de Experiencia donde apliquen.`
        );
      } else if (audit.atsData.missing_keywords && audit.atsData.missing_keywords.length > 0) {
        keywordConstraints.push(
          `KEYWORDS ATS FALTANTES DETECTADAS — Considera incorporar de forma natural las más relevantes que el candidato realmente posea: ${audit.atsData.missing_keywords.slice(0, 5).join(', ')}.`
        );
      }

      // Include AI detection score target to prevent the AI from over-writing in a robotic style
      if (typeof audit.atsData.ai_detection_score === 'number' && audit.atsData.ai_detection_score > 20) {
        keywordConstraints.push(
          `TONO DE REDACCIÓN: El score de detección de IA actual es ${audit.atsData.ai_detection_score}% (riesgo ${audit.atsData.ai_detection_score > 50 ? 'ALTO' : 'MEDIO'}). Usa un lenguaje más humano, concreto y directo. Evita frases genéricas como "apasionado por", "orientado a resultados" o verbos ampulosos sin métricas.`
        );
      }

      if (keywordConstraints.length > 0) {
        compiledParts.push(
          "⚠️ RESTRICCIONES ATS OBLIGATORIAS (MÁXIMA PRIORIDAD — no negociables):\n" +
          keywordConstraints.join('\n')
        );
      }
    }

    if (audit.selectedTips.length > 0) {
      compiledParts.push("CONSEJOS Y MEJORAS SELECCIONADAS POR EL USUARIO PARA APLICAR EN EL CV:\n" + audit.selectedTips.map(t => `- ${t}`).join('\n'));
    }
    if (customPrompt.trim()) {
      compiledParts.push("INSTRUCCIONES ADICIONALES DEL USUARIO:\n" + customPrompt.trim());
    }
    const fullInstructions = compiledParts.join('\n\n');
    // Pass the generated PDF filename so the AI refines the current CV, not the original upload
    handleGenerate(fullInstructions, generatedPdfFilename || undefined);
  };

  return {
    status,
    setStatus,
    progress,
    setProgress,
    stepMessage,
    setStepMessage,
    errorMessage,
    setErrorMessage,
    downloadUrl,
    setDownloadUrl,
    generatedPdfFilename,
    setGeneratedPdfFilename,
    auditScores,
    translationMeta,
    lastOutputLanguage,
    forceTranslateToEnglish,
    setForceTranslateToEnglish,
    elapsedSeconds,
    lastGeneratedYaml,
    setLastGeneratedYaml,
    handleGenerate,
    handleRegenerateWithFeedback,
    resetGeneration,
  };
}

export type Generation = ReturnType<typeof useGeneration>;