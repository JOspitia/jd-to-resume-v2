import { useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft, RotateCcw } from 'lucide-react';

import { useProfile } from './hooks/useProfile';
import { useAudit } from './hooks/useAudit';
import { useGeneration } from './hooks/useGeneration';
import { useYamlEditor } from './hooks/useYamlEditor';
import type { Generation } from './hooks/useGeneration';
import type { YamlEditorOps } from './hooks/useYamlEditor';
import { apiUrl } from './lib/api';

import { Section } from './components/Section';
import { ProfileSelector } from './components/ProfileSelector';
import { CvUploader } from './components/CvUploader';
import { JobContext } from './components/JobContext';
import { AdvancedOptions } from './components/AdvancedOptions';
import { ActionBar } from './components/ActionBar';
import { GenerationProgress } from './components/GenerationProgress';
import { ResultsPanel } from './components/ResultsPanel';
import { YamlEditorPanel } from './components/YamlEditorPanel';
import { AuditPanel } from './components/AuditPanel';
import { PhotoField } from './components/PhotoField';
import { Button } from './components/ui/Button';
import { ThemeToggle } from './components/ThemeToggle';

/**
 * ToolApp — T2 of the UX refactor (specs S1-S12).
 *
 * Thin orchestrator: it wires the four hooks together and composes the
 * layout. Each step in the main flow is a `<Section number={n} title="…">`
 * with a numbered tag and a semantic <h2>. The ActionBar is the only
 * sticky element (spec S7) and the only thing it carries is the primary
 * "Generar CV" CTA — every secondary action (preview, audit, translate,
 * reset) lives in the ResultsPanel where it is contextually relevant.
 *
 * Layout order:
 *   1. PERFIL            — ProfileSelector
 *   2. TU CV             — CvUploader
 *   3. LA VACANTE        — JobContext
 *   4. OPCIONES          — AdvancedOptions (collapsible, default open on
 *                          first visit)
 *   - ActionBar (sticky bottom, full width, just Generate)
 *   - GenerationProgress (only while status === 'generating' || 'error')
 *   - ResultsPanel       (only when status === 'success')
 *   - YamlEditorPanel    (only when yamlReady)
 *   - AuditPanel         (only when atsData is set)
 *
 * Mobile-first: every section is full width on small screens and the
 * ActionBar spans the viewport. The page bottom padding (pb-44) ensures
 * the sticky bar never covers the last interactive element.
 */
export default function ToolApp({ onBack }: { onBack: () => void }) {
  const profile = useProfile();

  // Late-bound bridges (see spec S6 of yaml-editor-ux-refactor.md for the
  // construction-cycle story). Both `useGeneration` and `useYamlEditor` need
  // to reach back into the other hook's API, but the hooks can't depend on
  // each other at definition time. We resolve that here.
  const generationRef = useRef<Generation | null>(null);
  const yamlOpsRef = useRef<YamlEditorOps | null>(null);

  const handleMissingFile = useCallback(() => {
    const generation = generationRef.current;
    if (!generation) return;
    generation.setErrorMessage('Por favor selecciona un archivo PDF de currículum.');
    generation.setStatus('error');
  }, []);

  const audit = useAudit(profile, handleMissingFile);
  const generation = useGeneration({ profile, audit, yamlOpsRef });
  generationRef.current = generation;
  const yamlEditor = useYamlEditor({ profile, generation, audit });
  yamlOpsRef.current = yamlEditor.ops;

  /**
   * Resets the frontend state across every hook, then purges the backend
   * cache. Lives here because it is the one handler that touches several
   * hooks at once.
   */
  const handleResetProcess = async () => {
    profile.resetProfile();
    generation.resetGeneration();
    audit.resetAudit();
    yamlEditor.resetYamlEditor();
    try {
      await fetch(apiUrl('/api/clear-cache'), { method: 'POST' });
    } catch (e) {
      console.error('No se pudo limpiar la caché del backend:', e);
    }
  };

  return (
    <div className="min-h-screen text-foreground flex flex-col items-center pt-10 pb-44 px-4 md:px-8 selection:bg-primary selection:text-primary-foreground relative">
      {/* Top bar — back + reset, compact */}
      <div className="absolute top-4 left-4 flex items-center gap-2 z-20">
        <Button
          onClick={onBack}
          variant="outline"
          size="sm"
          aria-label="Volver a la landing page"
        >
          <ArrowLeft className="w-4 h-4" /> Volver
        </Button>
        <Button
          onClick={handleResetProcess}
          variant="destructive"
          size="sm"
          className="text-xs font-bold"
          aria-label="Reiniciar el proceso completo"
          title="Limpiar campos y borrar la caché de CVs para iniciar de nuevo"
        >
          <RotateCcw className="w-3.5 h-3.5" /> Nuevo
        </Button>
      </div>

      {/* Theme toggle — top right corner of ToolApp */}
      <div className="absolute top-4 right-4 flex items-center gap-2 z-20">
        <ThemeToggle />
      </div>

      {/* Compact header (was a 7xl hero, now 2xl-3xl) — spec S1 */}
      <motion.header
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center w-full max-w-5xl mt-4 mb-8 z-10"
      >
        <h1 className="text-2xl md:text-3xl font-extrabold font-serif tracking-tight text-foreground">
          Perfect Your Resume.{' '}
          <span className="text-blue-700 underline decoration-4 underline-offset-4 decoration-orange-500">
            Beat the ATS.
          </span>
        </h1>
        <p className="text-sm md:text-base text-muted-foreground mt-2">
          Subí tu CV, elegí el perfil, pegá la vacante — generamos un PDF
          adaptado en minutos.
        </p>
      </motion.header>

      {/* Main flow — numbered sections */}
      <div className="w-full max-w-5xl space-y-6 z-10">
        <Section number={1} title="PERFIL">
          <ProfileSelector
            domainGame={profile.domainGame}
            onChange={profile.setDomainGame}
          />
        </Section>

        <Section number={2} title="TU CV">
          <CvUploader
            file={profile.file}
            fileInputRef={profile.fileInputRef}
            onFileChange={profile.handleFileChange}
            extractLinkedinInfo={profile.extractLinkedinInfo}
            onExtractLinkedinChange={profile.setExtractLinkedinInfo}
          />
        </Section>

        <Section number={3} title="LA VACANTE">
          <JobContext
            jd={profile.jd}
            onJdChange={profile.setJd}
            step2Mode={profile.step2Mode}
            onStep2ModeChange={profile.setStep2Mode}
            targetRole={profile.targetRole}
            onTargetRoleChange={profile.setTargetRole}
            linkedinUrl={profile.linkedinUrl}
            onLinkedinUrlChange={profile.setLinkedinUrl}
            githubUrl={profile.githubUrl}
            onGithubUrlChange={profile.setGithubUrl}
            portfolioUrl={profile.portfolioUrl}
            onPortfolioUrlChange={profile.setPortfolioUrl}
          />

          <PhotoField
            preview={profile.photoPreview}
            error={profile.photoError}
            inputRef={profile.photoInputRef}
            onChange={profile.handlePhotoChange}
            onClear={profile.clearPhoto}
          />
        </Section>

        <Section number={4} title="OPCIONES AVANZADAS">
          <AdvancedOptions
            selectedTheme={profile.selectedTheme}
            onThemeChange={profile.setSelectedTheme}
            fitSinglePage={profile.fitSinglePage}
            onFitSinglePageChange={profile.setFitSinglePage}
            pageBreakSection={profile.pageBreakSection}
            onPageBreakSectionChange={profile.setPageBreakSection}
            autoValidateATS={profile.autoValidateATS}
            onAutoValidateAtsChange={profile.setAutoValidateATS}
            editBeforeGenerate={profile.editBeforeGenerate}
            onEditBeforeGenerateChange={profile.setEditBeforeGenerate}
            strictEditsOnly={profile.strictEditsOnly}
            onStrictEditsOnlyChange={profile.setStrictEditsOnly}
            customPrompt={profile.customPrompt}
            onCustomPromptChange={profile.setCustomPrompt}
          />
        </Section>

        {/* Generation progress (only while running) */}
        <GenerationProgress
          status={generation.status}
          progress={generation.progress}
          stepMessage={generation.stepMessage}
          elapsedSeconds={generation.elapsedSeconds}
          errorMessage={generation.errorMessage}
        />

        {/* Results panel (only on success) */}
        <ResultsPanel
          status={generation.status}
          downloadUrl={generation.downloadUrl}
          hasYamlSnapshot={!!generation.lastGeneratedYaml}
          atsStatus={audit.atsStatus}
          lastOutputLanguage={generation.lastOutputLanguage}
          auditScores={generation.auditScores}
          translationMeta={generation.translationMeta}
          scoreHistory={audit.scoreHistory}
          onReopenYamlEditor={yamlEditor.handleReopenYamlEditor}
          onAudit={() => audit.handleValidateATS()}
          onTranslate={() => {
            generation.setForceTranslateToEnglish(true);
            generation.handleGenerate();
          }}
          onReset={handleResetProcess}
        />

        {/* YAML editor overlay */}
        <YamlEditorPanel
          yamlContent={yamlEditor.yamlContent}
          yamlReady={yamlEditor.yamlReady}
          onYamlChange={yamlEditor.setYamlContent}
          yamlError={yamlEditor.yamlError}
          yamlRepairing={yamlEditor.yamlRepairing}
          yamlRepairNotice={yamlEditor.yamlRepairNotice}
          hasBackup={!!yamlEditor.yamlBackup}
          status={generation.status}
          atsStatus={audit.atsStatus}
          onRender={yamlEditor.handleRenderFromYaml}
          onRegenerate={yamlEditor.handleRegenerateYaml}
          onAudit={yamlEditor.handleAuditYaml}
          onRepair={yamlEditor.handleRepairYaml}
          onRestoreBackup={yamlEditor.handleRestoreYamlBackup}
          onClose={yamlEditor.handleCloseYamlEditor}
        />

        {/* ATS + AI-tone audit results */}
        <AuditPanel
          atsStatus={audit.atsStatus}
          atsData={audit.atsData}
          atsErrorMessage={audit.atsErrorMessage}
          selectedKeywords={audit.selectedKeywords}
          onToggleKeyword={audit.toggleKeyword}
          selectedTips={audit.selectedTips}
          onToggleTip={audit.toggleTip}
          status={generation.status}
          strictEditsOnly={profile.strictEditsOnly}
          onStrictEditsOnlyChange={profile.setStrictEditsOnly}
          onRegenerateWithFeedback={generation.handleRegenerateWithFeedback}
        />
      </div>

      {/* Sticky bottom — only the primary CTA lives here (spec S7, S8) */}
      <ActionBar
        status={generation.status}
        elapsedSeconds={generation.elapsedSeconds}
        hasFile={!!profile.file}
        onGenerate={generation.handleGenerate}
      />
    </div>
  );
}
