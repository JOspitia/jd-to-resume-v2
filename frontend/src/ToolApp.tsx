import React, { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, Play, Download, AlertCircle, CheckCircle, Eye, ArrowLeft, ShieldCheck, BarChart3, Sparkles, CheckCircle2, AlertTriangle, Edit3, RefreshCw } from 'lucide-react';

export default function ToolApp({ onBack }: { onBack: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [jd, setJd] = useState('');
  const [targetRole, setTargetRole] = useState('');
  const [githubUrl, setGithubUrl] = useState('');
  const [linkedinUrl, setLinkedinUrl] = useState('');
  const [status, setStatus] = useState<'idle' | 'generating' | 'success' | 'error'>('idle');
  const [progress, setProgress] = useState(0);
  const [stepMessage, setStepMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [downloadUrl, setDownloadUrl] = useState('');
  const [generatedPdfFilename, setGeneratedPdfFilename] = useState<string | null>(null);
  const [selectedTheme, setSelectedTheme] = useState<string>('sb2nov');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ATS & AI Detection states
  const [autoValidateATS, setAutoValidateATS] = useState(false);
  const [atsStatus, setAtsStatus] = useState<'idle' | 'analyzing' | 'success' | 'error'>('idle');
  const [atsData, setAtsData] = useState<any | null>(null);
  const [atsErrorMessage, setAtsErrorMessage] = useState('');

  // Score history — tracks ATS evolution across regeneration versions
  type ScoreEntry = { version: number; ats: number; ai: number; format: number; label: string };
  const [scoreHistory, setScoreHistory] = useState<ScoreEntry[]>([]);
  const generationVersionRef = useRef(0);

  // Refinement states
  const [selectedTips, setSelectedTips] = useState<string[]>([]);
  const [customPrompt, setCustomPrompt] = useState<string>('');

  const toggleTip = (tip: string) => {
    setSelectedTips(prev => 
      prev.includes(tip) ? prev.filter(t => t !== tip) : [...prev, tip]
    );
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleValidateATS = async () => {
    if (!file) {
      setErrorMessage("Por favor selecciona un archivo PDF de currículum.");
      setStatus('error');
      return;
    }
    if (!jd.trim()) {
      setErrorMessage("Por favor pega la oferta de empleo (Job Description).");
      setStatus('error');
      return;
    }

    setAtsStatus('analyzing');
    setAtsErrorMessage('');

    const formData = new FormData();
    formData.append("file", file);
    formData.append("jd", jd);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 40000); // 40 second timeout

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
        generationVersionRef.current += 1;
        setScoreHistory(prev => [
          ...prev,
          {
            version: generationVersionRef.current,
            ats: data.ats_score ?? 0,
            ai: data.ai_detection_score ?? 0,
            format: data.ats_formatting_score ?? 0,
            label: generationVersionRef.current === 1 ? 'Original' : `Refinado v${generationVersionRef.current - 1}`,
          }
        ]);
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      if (err.name === 'AbortError') {
        setAtsErrorMessage("La solicitud de análisis ATS agotó el tiempo de espera (40s). Por favor reintenta.");
      } else {
        setAtsErrorMessage(err.message || "Ocurrió un error inesperado al analizar el ATS.");
      }
      setAtsStatus('error');
    }
  };

  const handleGenerate = async (customInstructionsOverride?: string, baseResumeFilename?: string) => {
    if (!file) {
      setErrorMessage("Please select a resume PDF to upload.");
      setStatus('error');
      return;
    }
    if (!jd.trim()) {
      setErrorMessage("Please paste the job description.");
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
    
    // Create form data
    const formData = new FormData();
    formData.append("file", file);
    formData.append("jd", jd);
    if (targetRole) formData.append("target_role", targetRole);
    if (githubUrl) formData.append("github_url", githubUrl);
    if (linkedinUrl) formData.append("linkedin_url", linkedinUrl);
    if (customInstructionsOverride) {
      formData.append("custom_instructions", customInstructionsOverride);
    }
    formData.append("theme", selectedTheme);
    // Pass the previously generated PDF filename so the backend refines it instead of starting fresh
    if (baseResumeFilename) {
      formData.append("base_resume_filename", baseResumeFilename);
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
                if (data.download_url) {
                  const fullUrl = `http://localhost:8000${data.download_url}`;
                  setDownloadUrl(fullUrl);
                  // Extract and store just the filename for future refinement passes
                  const filename = data.download_url.split('/').pop() || null;
                  setGeneratedPdfFilename(filename);
                  setStatus('success');

                  // Auto re-audit: always re-audit on refinement passes; on first gen only if checkbox enabled
                  if (autoValidateATS || baseResumeFilename) {
                    handleValidateATS();
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
    }
  };

  const handleRegenerateWithFeedback = () => {
    const compiledParts: string[] = [];

    // CRITICAL: Inject ATS keyword constraints first so they are never sacrificed
    // when applying humanization tips or custom instructions
    if (atsData) {
      const keywordConstraints: string[] = [];

      // Include current score + target so the AI knows exactly what benchmark to beat
      if (typeof atsData.ats_score === 'number') {
        const targetScore = Math.min(atsData.ats_score + 20, 90);
        keywordConstraints.push(
          `SCORE ATS ACTUAL DEL CV: ${atsData.ats_score}%. OBJETIVO MÍNIMO A SUPERAR: ${targetScore}%. Debes mejorar la densidad y relevancia de keywords para alcanzar o superar ese umbral.`
        );
      }

      if (atsData.matched_keywords && atsData.matched_keywords.length > 0) {
        keywordConstraints.push(
          `KEYWORDS ATS YA DETECTADAS — DEBES CONSERVAR TODAS (no elimines ninguna): ${atsData.matched_keywords.join(', ')}.`
        );
      }

      if (atsData.missing_keywords && atsData.missing_keywords.length > 0) {
        keywordConstraints.push(
          `KEYWORDS ATS FALTANTES — DEBES INCORPORAR DE FORMA NATURAL EN EL CV (en bullet points, resumen o habilidades, usando las que el candidato realmente posea): ${atsData.missing_keywords.join(', ')}.`
        );
      }

      // Include AI detection score target to prevent the AI from over-writing in a robotic style
      if (typeof atsData.ai_detection_score === 'number' && atsData.ai_detection_score > 20) {
        keywordConstraints.push(
          `TONO DE REDACCIÓN: El score de detección de IA actual es ${atsData.ai_detection_score}% (riesgo ${atsData.ai_detection_score > 50 ? 'ALTO' : 'MEDIO'}). Usa un lenguaje más humano, concreto y directo. Evita frases genéricas como "apasionado por", "orientado a resultados" o verbos ampulosos sin métricas.`
        );
      }

      if (keywordConstraints.length > 0) {
        compiledParts.push(
          "⚠️ RESTRICCIONES ATS OBLIGATORIAS (MÁXIMA PRIORIDAD — no negociables):\n" +
          keywordConstraints.join('\n')
        );
      }
    }

    if (selectedTips.length > 0) {
      compiledParts.push("CONSEJOS Y MEJORAS SELECCIONADAS POR EL USUARIO PARA APLICAR EN EL CV:\n" + selectedTips.map(t => `- ${t}`).join('\n'));
    }
    if (customPrompt.trim()) {
      compiledParts.push("INSTRUCCIONES ADICIONALES DEL USUARIO:\n" + customPrompt.trim());
    }
    const fullInstructions = compiledParts.join('\n\n');
    // Pass the generated PDF filename so the AI refines the current CV, not the original upload
    handleGenerate(fullInstructions, generatedPdfFilename || undefined);
  };

  return (
    <div className="min-h-screen text-black flex flex-col items-center pt-16 pb-24 px-6 md:px-12 selection:bg-blue-600 selection:text-white relative">
      
      {/* Decorative Accent Badges */}
      <button onClick={onBack} className="absolute top-8 left-8 rm-btn bg-white hover:bg-gray-100 text-black px-4 py-2 flex items-center gap-2">
         <ArrowLeft className="w-5 h-5" /> Back
      </button>
      <div className="absolute top-12 right-12 rm-tag bg-blue-700 text-white px-3 py-1 rotate-[3deg]">100% FREE</div>

      <div className="w-full max-w-5xl space-y-12 z-10 relative">
        
        {/* Header Area */}
        <motion.div 
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center space-y-4 pt-10 pb-8"
        >
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-black leading-tight drop-shadow-sm font-serif">
            Perfect Your Resume.<br/>
            <span className="text-blue-700 underline decoration-4 underline-offset-8 decoration-orange-500">Beat the ATS.</span>
          </h1>
          <p className="text-xl md:text-2xl font-medium text-gray-800 max-w-2xl mx-auto mt-6">
            Upload your existing PDF and paste the job description. Our AI transforms it into a perfectly tailored masterpiece.
          </p>
        </motion.div>

        {/* Input Grid */}
        <div className="grid md:grid-cols-2 gap-10">
          
          {/* File Upload Section */}
          <motion.div 
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.1 }}
            className="rm-box p-8 md:p-10 flex flex-col bg-white relative"
          >
            <div className="absolute -top-4 -left-4 rm-tag bg-orange-500 text-white px-4 py-2 text-lg">STEP_1</div>
            <h2 className="text-2xl font-bold mb-6 font-serif mt-2">Upload Resume</h2>
            <div 
              className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-gray-400 bg-gray-50 hover:bg-white hover:border-blue-600 cursor-pointer transition-all duration-200 p-8 min-h-[250px]"
              onClick={() => fileInputRef.current?.click()}
            >
              <input 
                type="file" 
                className="hidden" 
                ref={fileInputRef} 
                accept="application/pdf"
                onChange={handleFileChange}
              />
              {file ? (
                <>
                  <div className="relative mb-4 flex items-center justify-center">
                    <svg className="w-16 h-16 text-red-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                      <polyline points="14 2 14 8 20 8"></polyline>
                    </svg>
                    <span className="absolute mt-2 font-bold text-red-600" style={{ fontSize: '12px' }}>PDF</span>
                  </div>
                  <p className="font-bold text-center break-words max-w-full text-lg">{file.name}</p>
                  <p className="text-gray-500 text-sm mt-2">Click to replace</p>
                </>
              ) : (
                <>
                  <Upload className="w-12 h-12 mb-4 text-gray-800" strokeWidth={1.5} />
                  <p className="font-bold text-center text-xl mb-1">Click to browse file</p>
                  <p className="text-gray-500 font-medium text-sm">Strictly PDF format (Max: 5MB)</p>
                </>
              )}
            </div>
          </motion.div>

          {/* Job Description Section */}
          <motion.div 
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.2 }}
            className="rm-box p-8 md:p-10 flex flex-col bg-white relative"
          >
            <div className="absolute -top-4 -left-4 rm-tag bg-orange-500 text-white px-4 py-2 text-lg">STEP_2</div>
            <h2 className="text-2xl font-bold mb-6 font-serif mt-2">Job Description</h2>
            <textarea 
              value={jd}
              onChange={(e) => setJd(e.target.value)}
              placeholder="Paste the target job description requirements here..."
              className="flex-1 w-full border-2 border-black bg-white p-5 font-sans resize-none focus:outline-none focus:ring-4 focus:ring-blue-100 min-h-[250px] text-lg placeholder-gray-500"
            />
          </motion.div>
        </div>

        {/* Optional Settings Range */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.25 }}
          className="rm-box p-8 md:p-10 flex flex-col bg-[#F3F4F6] relative"
        >
          <div className="absolute -top-4 -left-4 rm-tag bg-white text-black px-4 py-2 text-lg">OPTIONAL</div>
          <h2 className="text-xl font-bold mb-6 font-serif">Additional Context</h2>
          
          <div className="grid md:grid-cols-3 gap-6">
            <div className="flex flex-col gap-2">
              <label className="font-bold font-mono text-sm uppercase tracking-wide">Target Role Title</label>
              <input 
                type="text" 
                value={targetRole}
                onChange={e => setTargetRole(e.target.value)}
                placeholder="e.g. Senior Frontend Eng"
                className="w-full border-2 border-black bg-white p-3 font-sans focus:outline-none focus:ring-4 focus:ring-blue-100"
              />
            </div>
            
            <div className="flex flex-col gap-2">
              <label className="font-bold font-mono text-sm uppercase tracking-wide">LinkedIn Profile</label>
              <input 
                type="url" 
                value={linkedinUrl}
                onChange={e => setLinkedinUrl(e.target.value)}
                placeholder="https://linkedin.com/in/..."
                className="w-full border-2 border-black bg-white p-3 font-sans focus:outline-none focus:ring-4 focus:ring-blue-100"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="font-bold font-mono text-sm uppercase tracking-wide">GitHub / Portfolio</label>
              <input 
                type="url" 
                value={githubUrl}
                onChange={e => setGithubUrl(e.target.value)}
                placeholder="https://github.com/..."
                className="w-full border-2 border-black bg-white p-3 font-sans focus:outline-none focus:ring-4 focus:ring-blue-100"
              />
            </div>
          </div>

          {/* Theme Selector */}
          <div className="mt-8 border-t-2 border-gray-300 pt-6">
            <label className="font-bold font-mono text-sm uppercase tracking-wide block mb-3">
              🎨 Plantilla & Diseñador de PDF (Vectorial Typst / ATS)
            </label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { id: 'sb2nov', name: 'SB2Nov', badge: 'Silicon Valley / ATS', desc: 'Limpio y estructurado para Tech' },
                { id: 'classic', name: 'Classic', badge: 'Sobrio', desc: 'Tradicional, elegante y universal' },
                { id: 'moderncv', name: 'ModernCV', badge: 'Visual', desc: 'Detalles a color y tipografía moderna' },
                { id: 'classic_html', name: 'Classic HTML', badge: 'Playwright', desc: 'Renderizado web tradicional' },
              ].map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setSelectedTheme(t.id)}
                  className={`p-3.5 text-left border-2 transition-all flex flex-col justify-between ${
                    selectedTheme === t.id 
                      ? 'border-blue-700 bg-blue-50 font-bold shadow-[2px_2px_0px_0px_rgba(29,78,216,1)]' 
                      : 'border-black bg-white hover:bg-gray-50'
                  }`}
                >
                  <div>
                    <span className="text-xs font-mono px-1.5 py-0.5 bg-gray-200 text-black font-bold uppercase inline-block mb-1">
                      {t.badge}
                    </span>
                    <div className="text-sm font-serif font-bold text-black">{t.name}</div>
                  </div>
                  <div className="text-[11px] text-gray-600 mt-2 line-clamp-1">{t.desc}</div>
                </button>
              ))}
            </div>
          </div>
        </motion.div>

        {/* Generate & Validate Controls */}
        <motion.div 
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="flex flex-col items-center gap-4 mt-6"
        >
          {/* Primary action buttons row */}
          <div className="flex flex-col md:flex-row items-center justify-center gap-4 w-full">
            <button 
              onClick={() => handleGenerate()}
              disabled={status === 'generating'}
              className="rm-btn bg-blue-700 hover:bg-blue-800 text-white disabled:opacity-70 disabled:cursor-not-allowed px-10 py-5 text-xl flex items-center gap-3"
            >
              {status === 'generating' ? (
                <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }}>
                  <CheckCircle className="w-6 h-6" />
                </motion.div>
              ) : <Play className="w-6 h-6 fill-current" />}
              {status === 'generating' ? 'PROCESSING...' : 'GENERATE TAILORED RESUME'}
            </button>

            {/* Standalone ATS-only audit button */}
            <button
              onClick={handleValidateATS}
              disabled={atsStatus === 'analyzing' || !file || !jd.trim()}
              title={!file || !jd.trim() ? 'Sube un PDF y pega el JD primero' : 'Auditar el CV actual contra el JD sin generar uno nuevo'}
              className="rm-btn bg-yellow-400 hover:bg-yellow-500 text-black disabled:opacity-50 disabled:cursor-not-allowed px-8 py-5 text-lg flex items-center gap-3"
            >
              {atsStatus === 'analyzing' ? (
                <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}>
                  <BarChart3 className="w-6 h-6" />
                </motion.div>
              ) : <ShieldCheck className="w-6 h-6" />}
              {atsStatus === 'analyzing' ? 'ANALIZANDO...' : '📊 SOLO AUDITAR ATS'}
            </button>
          </div>

          {/* Auto ATS Checkbox Option */}
          <label className="flex items-center gap-3 bg-white border-2 border-black p-4 font-mono font-bold cursor-pointer hover:bg-gray-50 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] select-none">
            <input 
              type="checkbox"
              checked={autoValidateATS}
              onChange={(e) => setAutoValidateATS(e.target.checked)}
              className="w-5 h-5 accent-blue-700 cursor-pointer"
            />
            <span className="text-sm md:text-base">Validar automáticamente match ATS al finalizar generación</span>
          </label>
        </motion.div>


        {/* Status Area */}
        <AnimatePresence mode="popLayout">
          {status !== 'idle' && (
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className={`rm-box p-10 mt-8 mx-auto max-w-3xl transform rotate-1 ${
                status === 'generating' ? 'bg-white' : 
                status === 'success' ? 'bg-[#f0fdf4]' : 
                'bg-[#fef2f2]'
              }`}
            >
              {status === 'generating' && (
                <div className="space-y-6">
                  <div className="flex justify-between items-end border-b-2 border-black pb-4">
                    <h3 className="text-2xl font-bold font-serif">{stepMessage}</h3>
                    <span className="text-3xl font-black font-mono">{progress}%</span>
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

              {status === 'success' && (
                <div className="space-y-8 flex flex-col items-center text-center">
                  <div className="inline-block bg-white rounded-full p-4 border-2 border-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
                    <CheckCircle className="w-16 h-16 text-green-600" />
                  </div>
                  <div>
                    <h3 className="text-4xl font-bold font-serif mb-4">Resume Generated!</h3>
                    <p className="text-xl text-gray-800">Your tailored, ATS-friendly PDF is ready for review.</p>
                  </div>
                  
                  <div className="flex flex-col md:flex-row justify-center gap-4 w-full">
                    <a 
                      href={downloadUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="rm-btn bg-white hover:bg-gray-50 flex-1 flex justify-center items-center gap-3 px-6 py-4 text-base font-bold"
                    >
                      <Eye className="w-5 h-5" /> PREVIEW
                    </a>
                    
                    <a 
                      href={downloadUrl}
                      download="Tailored_Resume.pdf"
                      target="_blank"
                      className="rm-btn bg-orange-500 text-white hover:bg-orange-600 flex-1 flex justify-center items-center gap-3 px-6 py-4 text-base font-bold"
                    >
                      <Download className="w-5 h-5" /> DOWNLOAD PDF
                    </a>

                    {/* Manual ATS & AI Validation Button */}
                    <button
                      onClick={handleValidateATS}
                      disabled={atsStatus === 'analyzing'}
                      className="rm-btn bg-yellow-400 text-black hover:bg-yellow-500 flex-1 flex justify-center items-center gap-3 px-6 py-4 text-base font-bold"
                    >
                      <BarChart3 className="w-5 h-5" />
                      {atsStatus === 'analyzing' ? 'ANALIZANDO ATS & IA...' : '📊 AUDITAR MATCH ATS & DETECCIÓN IA'}
                    </button>
                  </div>
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Score History Timeline */}
        {scoreHistory.length > 1 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="rm-box p-6 bg-white border-2 border-black relative"
          >
            <div className="absolute -top-4 -left-4 rm-tag bg-black text-white px-4 py-2 text-sm font-black">📈 EVOLUCIÓN DE SCORES</div>
            <div className="flex flex-wrap items-end gap-4 mt-2 pt-2">
              {scoreHistory.map((entry, i) => {
                const prev = scoreHistory[i - 1];
                const delta = prev ? entry.ats - prev.ats : null;
                return (
                  <div key={i} className={`flex flex-col items-center gap-1 p-3 border-2 min-w-[90px] ${
                    delta === null ? 'border-gray-400 bg-gray-50' :
                    delta > 0 ? 'border-green-500 bg-green-50' :
                    delta < 0 ? 'border-red-400 bg-red-50' : 'border-gray-400 bg-gray-50'
                  }`}>
                    <span className="font-mono text-xs text-gray-500 font-bold">{entry.label}</span>
                    <span className={`text-3xl font-black font-mono ${
                      entry.ats >= 75 ? 'text-green-600' : entry.ats >= 55 ? 'text-yellow-600' : 'text-red-600'
                    }`}>{entry.ats}%</span>
                    {delta !== null && (
                      <span className={`text-xs font-bold ${delta > 0 ? 'text-green-600' : delta < 0 ? 'text-red-500' : 'text-gray-400'}`}>
                        {delta > 0 ? `▲ +${delta}%` : delta < 0 ? `▼ ${delta}%` : '— sin cambio'}
                      </span>
                    )}
                    <span className="text-xs text-gray-400 font-mono">ATS Match</span>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}

        {/* ATS & AI Detection Audit Results Section */}
        <AnimatePresence>
          {atsStatus !== 'idle' && (
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="rm-box p-8 md:p-10 bg-white border-4 border-black relative"
            >
              <div className="absolute -top-4 -left-4 rm-tag bg-yellow-400 text-black px-4 py-2 text-lg font-black flex items-center gap-2">
                <ShieldCheck className="w-5 h-5" /> AUDITORÍA ATS & TONO HUMANO (CompuTrabajo Style)
              </div>

              {atsStatus === 'analyzing' && (
                <div className="py-12 flex flex-col items-center justify-center space-y-4">
                  <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}>
                    <BarChart3 className="w-16 h-16 text-blue-700" />
                  </motion.div>
                  <p className="text-xl font-bold font-serif">Analizando palabras clave, coincidencia ATS y nivel de redacción por IA...</p>
                </div>
              )}

              {atsStatus === 'error' && (
                <div className="p-6 bg-red-50 border-2 border-red-500 text-red-700 rounded-none flex items-center gap-4">
                  <AlertCircle className="w-10 h-10 shrink-0" />
                  <div>
                    <h4 className="font-bold text-lg">Error en Auditoría ATS</h4>
                    <p>{atsErrorMessage}</p>
                  </div>
                </div>
              )}

              {atsStatus === 'success' && atsData && (
                <div className="space-y-10 mt-4">
                  
                  {/* Scores Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    
                    {/* ATS Match Score */}
                    <div className="rm-box p-6 bg-blue-50 text-center flex flex-col items-center justify-center">
                      <span className="font-mono font-bold text-xs uppercase text-blue-900 tracking-wider mb-2">Match ATS (CompuTrabajo)</span>
                      <div className={`text-6xl font-black font-mono my-2 ${
                        atsData.ats_score >= 80 ? 'text-green-600' :
                        atsData.ats_score >= 60 ? 'text-yellow-600' : 'text-red-600'
                      }`}>
                        {atsData.ats_score}%
                      </div>
                      <span className="rm-tag bg-black text-white text-xs px-3 py-1 font-bold">
                        Nivel {atsData.match_level || 'Medio'}
                      </span>
                    </div>

                    {/* AI Tone / Human Risk Score */}
                    <div className="rm-box p-6 bg-purple-50 text-center flex flex-col items-center justify-center">
                      <span className="font-mono font-bold text-xs uppercase text-purple-900 tracking-wider mb-2">Detección de Tono IA</span>
                      <div className={`text-6xl font-black font-mono my-2 ${
                        atsData.ai_detection_score <= 20 ? 'text-green-600' :
                        atsData.ai_detection_score <= 50 ? 'text-yellow-600' : 'text-red-600'
                      }`}>
                        {atsData.ai_detection_score}%
                      </div>
                      <span className="text-xs font-bold text-gray-800 px-2 py-1">
                        {atsData.ai_tone_verdict || 'Análisis de Redacción'}
                      </span>
                    </div>

                    {/* ATS Format Score */}
                    <div className="rm-box p-6 bg-green-50 text-center flex flex-col items-center justify-center">
                      <span className="font-mono font-bold text-xs uppercase text-green-900 tracking-wider mb-2">Legibilidad & Formato</span>
                      <div className="text-6xl font-black font-mono my-2 text-green-700">
                        {atsData.ats_formatting_score || 95}%
                      </div>
                      <span className="text-xs font-bold text-green-800">
                        1 Página & Estructura Limpia
                      </span>
                    </div>
                  </div>

                  {/* Keywords Comparison */}
                  <div className="grid md:grid-cols-2 gap-8">
                    
                    {/* Matched Keywords */}
                    <div className="rm-box p-6 bg-white">
                      <h4 className="font-bold text-lg font-serif mb-4 flex items-center gap-2 text-green-700">
                        <CheckCircle2 className="w-5 h-5" /> Palabras Clave Detectadas ({atsData.matched_keywords?.length || 0})
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {atsData.matched_keywords && atsData.matched_keywords.length > 0 ? (
                          atsData.matched_keywords.map((kw: string, i: number) => (
                            <span key={i} className="rm-tag bg-green-100 border border-green-600 text-green-900 px-3 py-1 font-bold text-sm">
                              ✓ {kw}
                            </span>
                          ))
                        ) : (
                          <p className="text-gray-500 text-sm">No se detectaron palabras clave coincidentes.</p>
                        )}
                      </div>
                    </div>

                    {/* Missing Keywords */}
                    <div className="rm-box p-6 bg-white">
                      <h4 className="font-bold text-lg font-serif mb-4 flex items-center gap-2 text-orange-700">
                        <AlertTriangle className="w-5 h-5" /> Palabras Clave Faltantes ({atsData.missing_keywords?.length || 0})
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {atsData.missing_keywords && atsData.missing_keywords.length > 0 ? (
                          atsData.missing_keywords.map((kw: string, i: number) => (
                            <span key={i} className="rm-tag bg-orange-100 border border-orange-500 text-orange-900 px-3 py-1 font-bold text-sm">
                              + {kw}
                            </span>
                          ))
                        ) : (
                          <p className="text-gray-500 text-sm">¡Excelente! No faltan palabras clave principales.</p>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Selectable AI Humanize & Actionable Tips */}
                  <div className="grid md:grid-cols-2 gap-8">
                    
                    {/* AI Humanization Feedback */}
                    {atsData.ai_humanize_tips && atsData.ai_humanize_tips.length > 0 && (
                      <div className="rm-box p-6 bg-purple-50">
                        <h4 className="font-bold text-lg font-serif mb-2 flex items-center gap-2 text-purple-900">
                          <Sparkles className="w-5 h-5 text-purple-700" /> Consejos para Humanizar el Tono
                        </h4>
                        <p className="text-xs text-purple-800 font-medium mb-4">Marca las casillas que deseas aplicar al regenerar:</p>
                        <div className="space-y-3">
                          {atsData.ai_humanize_tips.map((tip: string, i: number) => (
                            <label key={i} className="flex items-start gap-3 cursor-pointer p-2 border border-purple-200 hover:border-purple-600 bg-white/70 hover:bg-white transition-all select-none">
                              <input 
                                type="checkbox"
                                checked={selectedTips.includes(tip)}
                                onChange={() => toggleTip(tip)}
                                className="w-4 h-4 mt-1 accent-purple-700 cursor-pointer shrink-0"
                              />
                              <span className="text-sm font-medium text-gray-900">{tip}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Actionable ATS Tips */}
                    {atsData.actionable_tips && atsData.actionable_tips.length > 0 && (
                      <div className="rm-box p-6 bg-yellow-50">
                        <h4 className="font-bold text-lg font-serif mb-2 flex items-center gap-2 text-yellow-900">
                          <BarChart3 className="w-5 h-5 text-yellow-800" /> Recomendaciones para Subir de Rango
                        </h4>
                        <p className="text-xs text-yellow-800 font-medium mb-4">Marca las casillas que deseas aplicar al regenerar:</p>
                        <div className="space-y-3">
                          {atsData.actionable_tips.map((tip: string, i: number) => (
                            <label key={i} className="flex items-start gap-3 cursor-pointer p-2 border border-yellow-300 hover:border-yellow-600 bg-white/70 hover:bg-white transition-all select-none">
                              <input 
                                type="checkbox"
                                checked={selectedTips.includes(tip)}
                                onChange={() => toggleTip(tip)}
                                className="w-4 h-4 mt-1 accent-yellow-600 cursor-pointer shrink-0"
                              />
                              <span className="text-sm font-medium text-gray-900">{tip}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Refinement Area: Custom Prompt Textarea + Regeneration Button */}
                  <div className="rm-box p-6 md:p-8 bg-blue-50 border-2 border-black space-y-4">
                    <h4 className="font-bold text-xl font-serif flex items-center gap-2 text-blue-900">
                      <Edit3 className="w-6 h-6 text-blue-700" /> Ajustar & Regenerar CV con Mejoras Seleccionadas
                    </h4>
                    <p className="text-sm text-gray-700 font-medium">
                      Has seleccionado <span className="font-bold text-purple-800">{selectedTips.length}</span> consejo(s). Puedes agregar indicaciones o ajustes adicionales abajo antes de hacer clic en regenerar:
                    </p>
                    <textarea 
                      value={customPrompt}
                      onChange={(e) => setCustomPrompt(e.target.value)}
                      placeholder="Ejemplo: Resalta mis 3 años de experiencia en pruebas de integración, pon el título profesional 'QA Specialist' y enfatiza mi manejo de automatización..."
                      className="w-full border-2 border-black bg-white p-4 font-sans focus:outline-none focus:ring-4 focus:ring-blue-100 min-h-[100px] text-base placeholder-gray-400"
                    />
                    <div className="flex justify-end pt-2">
                      <button
                        onClick={handleRegenerateWithFeedback}
                        disabled={status === 'generating'}
                        className="rm-btn bg-purple-700 text-white hover:bg-purple-800 disabled:opacity-50 px-8 py-4 text-lg font-bold flex items-center gap-3"
                      >
                        <RefreshCw className={`w-5 h-5 ${status === 'generating' ? 'animate-spin' : ''}`} />
                        {status === 'generating' ? 'REGENERANDO CV...' : '🔄 REGENERAR CV CON MEJORAS SELECCIONADAS'}
                      </button>
                    </div>
                  </div>

                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </div>
  );
}


