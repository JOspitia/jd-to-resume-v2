import { useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft, RotateCcw } from 'lucide-react';

import { useProfile } from './hooks/useProfile';
import { useAudit } from './hooks/useAudit';
import { useGeneration } from './hooks/useGeneration';
import { useYamlEditor } from './hooks/useYamlEditor';
import type { Generation } from './hooks/useGeneration';
import type { YamlEditorOps } from './hooks/useYamlEditor';

import { ProfileSelector } from './components/ProfileSelector';
import { CvUploader } from './components/CvUploader';
import { JobContext } from './components/JobContext';
import { AdvancedOptions } from './components/AdvancedOptions';
import { ActionBar } from './components/ActionBar';
import { GenerationProgress } from './components/GenerationProgress';
import { ResultsPanel } from './components/ResultsPanel';
import { YamlEditorPanel } from './components/YamlEditorPanel';
import { AuditPanel } from './components/AuditPanel';

/**
 * ToolApp — T15 of the UX refactor (specs S1-S7).
 *
 * Thin orchestrator: it wires the four hooks together and composes the layout.
 * All the logic lives in `hooks/` and all the markup in `components/`.
 *
 * Layout (adaptive, S1): the main flow is always visible — profile, uploader,
 * job context, advanced options — and the contextual surfaces (progress,
 * results, YAML editor, ATS audit) appear below / over it when relevant.
 */
export default function ToolApp({ onBack }: { onBack: () => void }) {
  const profile = useProfile();

  // Late-bound bridges. `useGeneration` and `useAudit` depend on each other
  // (the SSE reader re-runs the audit; the audit reports a missing file in the
  // generation status area) and the SSE reader opens the YAML editor panel
  // owned by `useYamlEditor`. Both dependencies travel through refs that are
  // filled in right below each hook; every handler dereferences them at call
  // time, long after the construction cycle is resolved.
  const generationRef = useRef<Generation | null>(null);
  const yamlOpsRef = useRef<YamlEditorOps | null>(null);

  const handleMissingFile = useCallback(() => {
    const generation = generationRef.current;
    if (!generation) return;
    generation.setErrorMessage("Por favor selecciona un archivo PDF de currículum.");
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

    // Call backend to purge cached PDFs and temp outputs
    try {
      await fetch("http://localhost:8000/api/clear-cache", {
        method: "POST",
      });
    } catch (e) {
      console.error("No se pudo limpiar la caché del backend:", e);
    }
  };

  return (
    <div className="min-h-screen text-black flex flex-col items-center pt-16 pb-44 px-6 md:px-12 selection:bg-blue-600 selection:text-white relative">
      {/* Decorative Accent Badges & Action Buttons */}
      <div className="absolute top-8 left-8 flex items-center gap-3">
        <button onClick={onBack} className="rm-btn bg-white hover:bg-gray-100 text-black px-4 py-2 flex items-center gap-2">
          <ArrowLeft className="w-5 h-5" /> Back
        </button>
        <button
          onClick={handleResetProcess}
          title="Limpiar campos y borrar la caché de CVs para iniciar de nuevo"
          className="rm-btn bg-rose-100 hover:bg-rose-200 border-rose-600 text-rose-900 px-4 py-2 flex items-center gap-2 text-sm font-bold shadow-[2px_2px_0px_0px_rgba(225,29,72,1)]"
        >
          <RotateCcw className="w-4 h-4 text-rose-700" /> Nuevo / Limpiar
        </button>
      </div>
      <div className="absolute top-12 right-12 rm-tag bg-blue-700 text-white px-3 py-1 rotate-[3deg]">100 % FREE</div>

      <div className="w-full max-w-5xl space-y-10 z-10 relative">
        {/* Header Area */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center space-y-4 pt-10 pb-8"
        >
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-black leading-tight drop-shadow-sm font-serif">
            Perfect Your Resume. <br />
            <span className="text-blue-700 underline decoration-4 underline-offset-8 decoration-orange-500">Beat the ATS.</span>
          </h1>
          <p className="text-xl md:text-2xl font-medium text-gray-800 max-w-2xl mx-auto mt-6">
            Upload your existing PDF and paste the job description.Our AI transforms it into a perfectly tailored masterpiece.
          </p>
        </motion.div>

        {/* 1 · Domain profile — the product differentiator, always on top (S7) */}
        <ProfileSelector domainGame={profile.domainGame} onChange={profile.setDomainGame} />

        {/* 2-3 · Main flow: source document + job context (S1) */}
        <div className="grid md:grid-cols-2 gap-10">
          <CvUploader
            file={profile.file}
            fileInputRef={profile.fileInputRef}
            onFileChange={profile.handleFileChange}
            extractLinkedinInfo={profile.extractLinkedinInfo}
            onExtractLinkedinChange={profile.setExtractLinkedinInfo}
          />
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
        </div>

        {/* 4 · Advanced options — collapsed for the ~80% who never touch them (S2) */}
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

        {/* 5 · Fixed action bar (S3) */}
        <ActionBar
          status={generation.status}
          atsStatus={audit.atsStatus}
          elapsedSeconds={generation.elapsedSeconds}
          hasFile={!!profile.file}
          lastOutputLanguage={generation.lastOutputLanguage}
          showReset={!!(profile.file || profile.jd || generation.status !== 'idle' || audit.atsStatus !== 'idle')}
          onGenerate={generation.handleGenerate}
          onAudit={() => audit.handleValidateATS()}
          onReset={handleResetProcess}
        />

        {/* 6 · Live progress + failures */}
        <GenerationProgress
          status={generation.status}
          progress={generation.progress}
          stepMessage={generation.stepMessage}
          elapsedSeconds={generation.elapsedSeconds}
          errorMessage={generation.errorMessage}
        />

        {/* 7 · Results — below the main flow, never replacing it (S4) */}
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

        {/* 8 · YAML editor — contextual overlay over the main flow (S5) */}
        <YamlEditorPanel
          yamlContent={yamlEditor.yamlContent}
          yamlReady={yamlEditor.yamlReady}
          onYamlChange={yamlEditor.setYamlContent}
          yamlError={yamlEditor.yamlError}
          yamlRepairing={yamlEditor.yamlRepairing}
          yamlRepairNotice={yamlEditor.yamlRepairNotice}
          status={generation.status}
          atsStatus={audit.atsStatus}
          onRender={yamlEditor.handleRenderFromYaml}
          onRegenerate={yamlEditor.handleRegenerateYaml}
          onAudit={yamlEditor.handleAuditYaml}
          onRepair={yamlEditor.handleRepairYaml}
          onClose={yamlEditor.handleCloseYamlEditor}
        />

        {/* 9 · ATS + AI-tone audit results */}
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
    </div>
  );
}