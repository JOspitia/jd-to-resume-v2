import { motion } from 'framer-motion';
import { Upload } from 'lucide-react';
import type { ChangeEvent, RefObject } from 'react';

/**
 * CvUploader — T6 of the UX refactor (specs S1, S6).
 *
 * Step 1 of the main flow: the PDF drop zone plus the "extract LinkedIn
 * info" toggle, both bound to the `useProfile` state that feeds the
 * `/api/generate` FormData (`file`, `extract_linkedin_info`).
 */

export type CvUploaderProps = {
  file: File | null;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onFileChange: (e: ChangeEvent<HTMLInputElement>) => void;
  extractLinkedinInfo: boolean;
  onExtractLinkedinChange: (checked: boolean) => void;
};

export function CvUploader({
  file,
  fileInputRef,
  onFileChange,
  extractLinkedinInfo,
  onExtractLinkedinChange,
}: CvUploaderProps) {
  return (
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
          onChange={onFileChange}
        />
        {file ? (
          <>
            <div className="relative mb-4 flex items-center justify-center">
              <svg
                className="w-16 h-16 text-red-600"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
              </svg>
              <span className="absolute mt-2 font-bold text-red-600" style={{ fontSize: '12px' }}>
                PDF
              </span>
            </div>
            <p className="font-bold text-center break-words max-w-full text-lg">{file.name}</p>
            <p className="text-gray-500 text-sm mt-2">Click to replace</p>
          </>
        ) : (
          <>
            <Upload className="w-12 h-12 mb-4 text-gray-800" strokeWidth={1.5} />
            <p className="font-bold text-center text-xl mb-1">Click to browse file</p>
            <p className="text-gray-500 font-medium text-sm">Strictly PDF format(Max: 5MB)</p>
          </>
        )}
      </div>

      {/* Only extract LinkedIn info on first generation — not on refinement passes (no need to re-scrape).
          The checkbox sits next to the uploader so the "scrape my profile" decision is made while the user
          is thinking about the source document; the LinkedIn URL itself lives in <JobContext />. */}
      <label className="flex items-center gap-3 bg-white border-2 border-black p-4 font-mono font-bold cursor-pointer hover:bg-gray-50 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] select-none mt-6">
        <input
          type="checkbox"
          checked={extractLinkedinInfo}
          onChange={(e) => onExtractLinkedinChange(e.target.checked)}
          className="w-5 h-5 accent-blue-700 cursor-pointer"
        />
        <span className="text-sm md:text-base">Extraer e integrar información del perfil</span>
      </label>
    </motion.div>
  );
}

export default CvUploader;