import { useState } from 'react';
import type { Profile } from './useProfile';
import type { Generation } from './useGeneration';
import type { Audit } from './useAudit';
import { validateYaml } from '../lib/yamlValidator';

/**
 * useYamlEditor — T3 of the UX refactor (specs S5, S6).
 *
 * Owns the edit-before-generate YAML panel: the textarea content, the panel
 * visibility and the four actions the user can take on it (render, discard +
 * regenerate, audit, AI-assisted repair).
 */

type YamlEditorDeps = {
  profile: Pick<
    Profile,
    | 'jd'
    | 'domainGame'
    | 'selectedTheme'
    | 'fitSinglePage'
    | 'pageBreakSection'
    | 'customPrompt'
    | 'autoValidateATS'
    | 'setEditBeforeGenerate'
  >;
  generation: Generation;
  audit: Audit;
};

/**
 * Slice of the editor that `useGeneration` needs in order to react to the
 * `yaml_ready` SSE event without owning the editor state itself.
 */
export type YamlEditorOps = {
  /** Stash the streamed YAML and open the editor panel. */
  open: (yaml: string) => void;
};

export function useYamlEditor({ profile, generation, audit }: YamlEditorDeps) {
  const {
    jd,
    domainGame,
    selectedTheme,
    fitSinglePage,
    pageBreakSection,
    customPrompt,
    autoValidateATS,
    setEditBeforeGenerate,
  } = profile;

  const [yamlContent, setYamlContent] = useState<string | null>(null);
  const [yamlReady, setYamlReady] = useState(false);
  const [yamlError, setYamlError] = useState('');
  // Repair flow — see handleRepairYaml (below). Used by the "🤖 Reparar YAML con IA"
  // button to display a transient notice ("Cambios aplicados: …") after the user
  // requests an AI-assisted YAML repair.
  const [yamlRepairing, setYamlRepairing] = useState(false);
  const [yamlRepairNotice, setYamlRepairNotice] = useState('');

  const {
    setStatus,
    setProgress,
    setStepMessage,
    setDownloadUrl,
    setGeneratedPdfFilename,
    setLastGeneratedYaml,
    handleGenerate,
  } = generation;
  const {
    setAtsStatus,
    setAtsData,
    setAtsErrorMessage,
    handleValidateATS,
    recordScore,
    generationVersionRef,
  } = audit;

  const open: YamlEditorOps['open'] = (yaml) => {
    setYamlContent(yaml);
    setYamlReady(true);
    setYamlError('');
  };

  // handleRenderFromYaml: POST the user-edited YAML to /api/render-from-yaml
  // and treat the response like a successful /api/generate (download_url,
  // status='success', close the editor).
  const handleRenderFromYaml = async () => {
    if (!yamlContent) {
      setYamlError('No hay contenido YAML para renderizar.');
      return;
    }

    // --- Auto-cleanup: if the YAML is broken, ask the IA to fix it first. ---
    let renderableYaml = yamlContent;
    const validation = validateYaml(yamlContent);
    if (!validation.valid) {
      setYamlRepairing(true);
      setStepMessage(
        `YAML inválido (línea ${validation.line ?? '?'}): la IA lo está arreglando...`,
      );
      try {
        const repairFormData = new FormData();
        repairFormData.append('yaml_content', yamlContent);
        if (domainGame) repairFormData.append('domain_game', domainGame);

        const repairRes = await fetch(
          'http://localhost:8000/api/repair-yaml',
          { method: 'POST', body: repairFormData },
        );
        if (!repairRes.ok) {
          const errText = await repairRes.text().catch(() => '');
          throw new Error(
            `repair-yaml failed (${repairRes.status}): ${errText || repairRes.statusText}`,
          );
        }
        const repairData = await repairRes.json();
        if (typeof repairData?.yaml === 'string' && repairData.yaml.trim()) {
          // Validate the IA's output LOCALLY before accepting it. The IA
          // sometimes claims the YAML is valid but produces indentation
          // errors (e.g. `items:` at column 1 instead of under a list
          // item). We refuse the repair and show the user the actual
          // error so they can fix it manually.
          const reparValidation = validateYaml(repairData.yaml);
          if (!reparValidation.valid) {
            setYamlRepairing(false);
            setYamlError(
              `La IA no pudo reparar el YAML: el resultado sigue inválido (línea ${reparValidation.line ?? '?'}): ${reparValidation.error}. Editá manualmente o volvé a intentar.`,
            );
            return;
          }
          renderableYaml = repairData.yaml;
          setYamlContent(repairData.yaml);
          const repairs = Array.isArray(repairData.repairs) ? repairData.repairs : [];
          setYamlRepairNotice(
            repairs.length > 0
              ? `Tu YAML tenía errores. La IA los corrigió: ${repairs.join(' · ')}`
              : 'La IA revisó tu YAML y lo devolvió sin cambios.',
          );
        } else if (repairData?.error) {
          throw new Error(repairData.error);
        } else {
          throw new Error('La IA no pudo reparar el YAML (respuesta vacía).');
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setYamlRepairing(false);
        setYamlError(`No se pudo auto-arreglar el YAML: ${msg}`);
        return;
      }
      setYamlRepairing(false);
    }

    setYamlError('');
    setStatus('generating');
    setProgress(0);
    setStepMessage('Renderizando CV desde YAML...');

    const formData = new FormData();
    formData.append('yaml_content', renderableYaml);
    formData.append('theme', selectedTheme);
    formData.append('fit_single_page', fitSinglePage ? 'true' : 'false');
    if (pageBreakSection && pageBreakSection !== 'none') {
      formData.append('page_break_section', pageBreakSection);
    }
    if (jd) formData.append('jd', jd);
    if (customPrompt) formData.append('custom_instructions', customPrompt);
    if (domainGame) formData.append('domain_game', domainGame);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);
    try {
      const res = await fetch('http://localhost:8000/api/render-from-yaml', {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!res.ok) {
        const errText = await res.text().catch(() => '');
        throw new Error(`Render-from-YAML failed (${res.status}): ${errText || res.statusText}`);
      }
      const data = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }
      const downloadPath: string = data.download_url;
      const filename: string = data.filename || downloadPath.split('/').pop() || '';
      setDownloadUrl(`http://localhost:8000${downloadPath}`);
      setGeneratedPdfFilename(filename);
      setStatus('success');
      setStepMessage('CV renderizado');
      setProgress(100);
      // Snapshot the YAML that produced this PDF so the user can re-open
      // the editor later (via the "✏️ Modificar YAML y regenerar" button
      // on the success card). Keeps the iteration loop alive.
      if (yamlContent) {
        setLastGeneratedYaml(yamlContent);
      }
      // Close the YAML editor and reset the flag (S4).
      setYamlContent(null);
      setYamlReady(false);
      setEditBeforeGenerate(false);
      // Track the new version in scoreHistory as the next refinado.
      generationVersionRef.current += 1;

      // T8 of yaml-editor feature: if autoValidateATS is on, audit the freshly
      // rendered PDF (fetched from download_url) so the user gets the audit
      // without needing to click the standalone SOLO AUDITAR ATS button.
      // Network failures are swallowed silently so the success card stays
      // visible. Matches the original WIP-yaml spec T9.
      if (autoValidateATS) {
        try {
          const auditResp = await fetch(`http://localhost:8000${downloadPath}`);
          if (!auditResp.ok) {
            throw new Error(`audit fetch failed: ${auditResp.status}`);
          }
          const auditBlob = await auditResp.blob();
          const renderedFile = new File([auditBlob], filename, { type: 'application/pdf' });
          await handleValidateATS(renderedFile);
        } catch (auditErr) {
          // Silent on purpose: the success card is already showing and
          // the user can still trigger the audit manually.
          console.warn('[audit-after-render] failed (silent):', auditErr);
        }
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      const msg = err.name === 'AbortError'
        ? 'El render desde YAML agotó el tiempo de espera (1 min). Por favor reintenta.'
        : (err.message || 'Error desconocido al renderizar desde YAML.');
      setYamlError(msg);
      setStatus('error');
    }
  };

  // handleRegenerateYaml: re-invoke /api/generate with edit_before_generate=true
  // (the checkbox is still on). The LLM will run again and stream a new
  // yaml_ready event; the editor reopens.
  const handleRegenerateYaml = async () => {
    setYamlReady(false);
    setYamlError('');
    profile.setEditBeforeGenerate(true); // make sure the flag is on for the re-run
    // handleGenerate reads the current state of editBeforeGenerate via the
    // FormData, so the LLM will be re-invoked and the new yaml will arrive
    // via the existing SSE handler.
    await handleGenerate();
  };

  // handleAuditYaml: POST the user-edited YAML to /api/analyze-yaml.
  // The response is the same audit dict shape as /api/analyze-ats. We
  // stash it in atsData and close the editor. The user can then trigger
  // /api/render-from-yaml to render the audited content.
  const handleAuditYaml = async () => {
    if (!yamlContent) {
      setYamlError('No hay contenido YAML para validar.');
      return;
    }
    setYamlError('');
    setAtsStatus('analyzing');
    setAtsErrorMessage('');

    const formData = new FormData();
    formData.append('yaml_content', yamlContent);
    if (jd) formData.append('jd', jd);
    if (domainGame) formData.append('domain_game', domainGame);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);
    try {
      const res = await fetch('http://localhost:8000/api/analyze-yaml', {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!res.ok) {
        const errText = await res.text().catch(() => '');
        throw new Error(`Audit-from-YAML failed (${res.status}): ${errText || res.statusText}`);
      }
      const data = await res.json();
      if (data.error) {
        setAtsErrorMessage(data.error);
        setAtsStatus('error');
        return;
      }
      setAtsData(data);
      setAtsStatus('success');
      // `label` is evaluated before `recordScore` bumps the counter, which is
      // exactly the `YAML v{n-1}` the pre-refactor code produced.
      recordScore({
        ats: data.ats_score ?? 0,
        ai: data.ai_detection_score ?? 0,
        format: data.ats_formatting_score ?? 0,
        label: `YAML v${generationVersionRef.current}`,
      });
      // Close the YAML editor on success (S4). The user can then click
      // Generar CV to render with the audited YAML.
      setYamlReady(false);
      setEditBeforeGenerate(false);
    } catch (err: any) {
      clearTimeout(timeoutId);
      const msg = err.name === 'AbortError'
        ? 'La auditoría desde YAML agotó el tiempo de espera (1 min). Por favor reintenta.'
        : (err.message || 'Error desconocido al auditar desde YAML.');
      setYamlError(msg);
      setAtsStatus('error');
    }
  };

  // AI-assisted YAML repair: when the user accidentally broke the YAML
  // (indentation, missing colons, wrong types inside experience/skills/etc),
  // POST /api/repair-yaml attempts a local validation first and only hits
  // the LLM when needed. Replaces the textarea content with the repaired
  // YAML and shows a brief summary of what changed.
  const handleRepairYaml = async () => {
    if (!yamlContent) {
      setYamlError('El YAML está vacío. Pegá o generá una respuesta primero.');
      return;
    }
    setYamlRepairing(true);
    setYamlRepairNotice('');
    setYamlError('');

    try {
      const formData = new FormData();
      formData.append('yaml_content', yamlContent);

      const res = await fetch('http://localhost:8000/api/repair-yaml', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) throw new Error('No se pudo conectar con el endpoint de reparación YAML.');
      const data = await res.json();

      if (typeof data?.yaml === 'string') {
        // Validate the IA's output LOCALLY before accepting it. The IA
        // sometimes claims the YAML is valid but produces indentation
        // errors (e.g. `items:` at column 1 instead of under a list
        // item). We refuse the repair and show the user the actual
        // error so they can fix it manually.
        const reparValidation = validateYaml(data.yaml);
        if (!reparValidation.valid) {
          setYamlRepairing(false);
          setYamlError(
            `La IA no pudo reparar el YAML: el resultado sigue inválido (línea ${reparValidation.line ?? '?'}): ${reparValidation.error}. Editá manualmente o volvé a intentar.`,
          );
          return;
        }
        setYamlContent(data.yaml);
      } else if (data?.error) {
        setYamlError(data.error);
        return;
      } else {
        setYamlError('La IA no pudo reparar el YAML (respuesta vacía).');
        return;
      }
      const noticeParts: string[] = [];
      if (Array.isArray(data?.repairs) && data.repairs.length > 0) {
        noticeParts.push('Cambios aplicados: ' + data.repairs.join(' · '));
      }
      if (Array.isArray(data?.schema_errors) && data.schema_errors.length > 0) {
        noticeParts.push('Errores restantes que la IA no pudo resolver: ' + data.schema_errors.join(' · '));
      }
      setYamlRepairNotice(noticeParts.join('\n') || (data?.ok ? 'YAML válido — sin cambios.' : 'Reparación parcial.'));
    } catch (err: any) {
      setYamlError(err.message || 'Error al reparar el YAML.');
    } finally {
      setYamlRepairing(false);
    }
  };

  // Reopen the YAML editor after a CV has been generated. Restores the
  // snapshot of the YAML that produced the currently-displayed PDF into the
  // editable textarea so the user can iterate: edit → re-render → repeat.
  // No LLM call here — the snapshot is in memory.
  const handleReopenYamlEditor = () => {
    if (!generation.lastGeneratedYaml) {
      setYamlError('No hay un YAML previo para re-abrir. Regenerá el CV desde el checkbox "Editar antes de generar".');
      return;
    }
    setYamlContent(generation.lastGeneratedYaml);
    setYamlReady(true);
    setYamlError('');
    setEditBeforeGenerate(false);
  };

  // Dismiss the YAML editor without re-rendering. Returns the user to the
  // success card. Used as an explicit exit from the editor panel.
  const handleCloseYamlEditor = () => {
    setYamlContent(null);
    setYamlReady(false);
    setYamlError('');
    setYamlRepairNotice('');
    setEditBeforeGenerate(false);
  };

  /** Clears the editor state used by the global "Nuevo / Limpiar" action. */
  const resetYamlEditor = () => {
    setYamlContent(null);
    setYamlReady(false);
    setYamlError('');
  };

  const ops: YamlEditorOps = { open };

  return {
    yamlContent,
    setYamlContent,
    yamlReady,
    yamlError,
    yamlRepairing,
    yamlRepairNotice,
    ops,
    handleRenderFromYaml,
    handleRegenerateYaml,
    handleAuditYaml,
    handleRepairYaml,
    handleReopenYamlEditor,
    handleCloseYamlEditor,
    resetYamlEditor,
  };
}

export type YamlEditor = ReturnType<typeof useYamlEditor>;