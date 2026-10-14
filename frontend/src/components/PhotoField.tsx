import { UserCircle2, X } from 'lucide-react';

import type { ChangeEvent } from 'react';

export type PhotoFieldProps = {
  preview: string | null;
  error: string;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
  onClear: () => void;
};

/**
 * PhotoField — optional candidate photo.
 *
 * RenderCV embeds the photo from a filesystem path, so the picked `File` is
 * passed straight through to the backend; this component only owns the
 * `<input>` and its local preview.
 *
 * Deliberately available for every domain. In Spain and LATAM a photo is
 * expected on HR and psychology CVs, while tech CVs are often submitted
 * without one — offering it everywhere with a plain explanation leaves the
 * choice to the candidate instead of encoding a rule that is wrong for some
 * recruiters and right for others.
 */
export function PhotoField({
  preview,
  error,
  inputRef,
  onChange,
  onClear,
}: PhotoFieldProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor="candidate-photo"
        className="font-bold font-mono text-xs uppercase tracking-wide text-gray-700 flex items-center gap-1.5"
      >
        <UserCircle2 className="w-3.5 h-3.5" /> Foto (opcional)
      </label>

      <input
        ref={inputRef}
        id="candidate-photo"
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        onChange={onChange}
        className="block w-full text-xs font-mono file:mr-3 file:border-2 file:border-black file:bg-gray-100 file:px-3 file:py-1.5 file:font-bold hover:file:bg-gray-200 cursor-pointer"
      />

      {preview && (
        <div className="flex items-center gap-3 mt-1 p-2 border-2 border-black bg-gray-50">
          <img
            src={preview}
            alt="Vista previa de la foto"
            className="w-14 h-14 rounded-full object-cover border-2 border-black shrink-0"
          />
          <span className="text-xs font-mono text-gray-700 flex-1">
            Se mostrará en el encabezado del CV.
          </span>
          <button
            type="button"
            onClick={onClear}
            title="Quitar la foto"
            aria-label="Quitar la foto"
            className="p-1.5 border-2 border-black bg-white hover:bg-rose-100 text-rose-700 shrink-0"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {error && (
        <p className="text-xs font-bold text-rose-700" role="alert">
          {error}
        </p>
      )}

      {!preview && (
        <p className="text-[11px] text-gray-500 italic">
          PNG, JPG, GIF o WebP. Hasta 5&nbsp;MB. Dejala vacía si preferís un CV
          sin fotografía.
        </p>
      )}
    </div>
  );
}

export default PhotoField;
