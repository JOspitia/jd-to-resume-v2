import { useState, type ChangeEvent, type DragEvent, type RefObject } from 'react';
import { UploadCloud, FileText } from 'lucide-react';

/**
 * CvUploader — T4 of the UX refactor (spec S9).
 *
 * Drop-zone with visual feedback: the dashed border thickens and the
 * background darkens on dragover, and the file name is shown prominently
 * once a file is selected. The "extract LinkedIn" toggle sits at the bottom
 * of the card, adjacent to the uploader so the "scrape my profile" decision
 * is made while the user is thinking about the source document.
 *
 * Wrapped by <Section number={2} title="TU CV"> in ToolApp.
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
  const [dragOver, setDragOver] = useState(false);

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(true);
  };
  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
  };
  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped && fileInputRef.current) {
      // Forward through the same <input type=file> change handler so
      // the rest of the pipeline (validation, state update) is identical
      // to the click-to-browse path.
      const dt = new DataTransfer();
      dt.items.add(dropped);
      fileInputRef.current.files = dt.files;
      const fakeEvent = { target: fileInputRef.current } as ChangeEvent<HTMLInputElement>;
      onFileChange(fakeEvent);
    }
  };

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`flex flex-col items-center justify-center border-2 border-dashed cursor-pointer transition-all duration-200 p-10 min-h-[220px] gap-3 ${
          dragOver
            ? 'border-blue-700 bg-blue-50 scale-[1.01]'
            : file
              ? 'border-emerald-600 bg-emerald-50/40'
              : 'border-gray-400 bg-gray-50 hover:bg-white hover:border-blue-600'
        }`}
      >
        <input
          type="file"
          className="hidden"
          ref={fileInputRef}
          accept="application/pdf"
          onChange={onFileChange}
          aria-label="Subir currículum en formato PDF"
        />
        {file ? (
          <>
            <FileText className="w-12 h-12 text-emerald-700" strokeWidth={1.5} />
            <p className="font-bold text-center break-words max-w-full text-lg">{file.name}</p>
            <p className="text-emerald-700 text-sm font-mono">Click to replace</p>
          </>
        ) : (
          <>
            <UploadCloud className="w-14 h-14 text-gray-700" strokeWidth={1.5} />
            <p className="font-bold text-center text-lg">
              {dragOver ? 'Soltá el PDF acá' : 'Arrastrá tu CV o hacé clic'}
            </p>
            <p className="text-gray-500 font-medium text-xs font-mono">PDF · máximo 5MB</p>
          </>
        )}
      </div>

      <label className="flex items-center gap-3 bg-white border-2 border-black p-3 font-mono font-bold cursor-pointer hover:bg-gray-50 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] select-none">
        <input
          type="checkbox"
          checked={extractLinkedinInfo}
          onChange={(e) => onExtractLinkedinChange(e.target.checked)}
          className="w-4 h-4 accent-blue-700 cursor-pointer"
        />
        <span className="text-sm">Extraer e integrar información del perfil de LinkedIn</span>
      </label>
    </div>
  );
}

export default CvUploader;
