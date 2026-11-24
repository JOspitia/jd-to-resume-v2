import { AnimatePresence, motion } from 'framer-motion';
import {
  CheckCircle2,
  Copy,
  Download,
  Eye,
  RefreshCw,
  FileText,
} from 'lucide-react';

import { Card } from './ui/Card';
import { Button } from './ui/Button';
import { Badge } from './ui/Badge';
import type { CoverLetter } from '../types/coverLetter';

/**
 * CoverLetterPanel — the success card of the cover-letter deliverable.
 *
 * Shows the generated letter the way it will be read (plain prose, no
 * headings, generous line height) and gives the three actions a letter
 * needs:
 *   * Copiar        → paste into the application form.
 *   * Descargar .txt → for portals that want a file.
 *   * Regenerar     → another take with the same inputs.
 *
 * The letter is rendered from the structured fields (salutation / opening
 * / body / closing / signature) so the panel and the copy buffer are
 * guaranteed to show the same text.
 */

export type CoverLetterPanelProps = {
  status: 'idle' | 'generating' | 'success' | 'error';
  letter: CoverLetter | null;
  copied: boolean;
  onCopy: () => void;
  onDownload: () => void;
  onRegenerate: () => void;
  /**
   * Opens the letter PDF inside the app (modal over the form).
   *
   * It used to be an `<a target="_blank">`, which in the embedded browser
   * replaces the current tab with the PDF viewer — the user came back to
   * a reloaded app (landing page, empty form).
   */
  onPreviewPdf: () => void;
  /** Saves the letter PDF to disk without navigating away from the app. */
  onDownloadPdf: () => void;
};

export function CoverLetterPanel({
  status,
  letter,
  copied,
  onCopy,
  onDownload,
  onRegenerate,
  onPreviewPdf,
  onDownloadPdf,
}: CoverLetterPanelProps) {
  const pdfUrl = letter?.pdf_url;

  return (
    <AnimatePresence mode="popLayout">
      {status === 'success' && letter && (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25 }}
        >
          <Card variant="success" size="lg" aria-labelledby="cover-letter-title">
            <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
              <div className="flex items-center gap-2.5">
                <CheckCircle2 className="w-6 h-6 text-success shrink-0" />
                <div>
                  <h2
                    id="cover-letter-title"
                    className="text-xl font-bold font-serif text-foreground"
                  >
                    Carta de presentación lista
                  </h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {letter.meta.word_count} palabras ·{' '}
                    {letter.meta.language === 'en'
                      ? 'en inglés'
                      : letter.meta.language === 'es'
                        ? 'en español'
                        : 'idioma por definir'}
                  </p>
                </div>
              </div>
              <Badge variant="success" size="sm">
                Lista para copiar
              </Badge>
            </div>

            {/* The letter itself — rendered as continuous prose. */}
            <div className="border-2 border-border bg-card p-5 sm:p-6 max-h-[520px] overflow-y-auto">
              <div className="font-serif text-[15px] leading-relaxed text-foreground space-y-4">
                {letter.salutation && <p>{letter.salutation}</p>}
                {letter.opening && <p>{letter.opening}</p>}
                {letter.body.map((paragraph, index) => (
                  <p key={index}>{paragraph}</p>
                ))}
                {letter.closing && <p>{letter.closing}</p>}
                {letter.signature && (
                  <p className="whitespace-pre-wrap font-sans text-sm font-bold">
                    {letter.signature}
                  </p>
                )}
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-2 mt-4">
              {pdfUrl ? (
                <>
                  <Button
                    onClick={onDownloadPdf}
                    variant="primary"
                    size="md"
                    aria-label="Descargar el PDF de la carta de presentación"
                  >
                    <Download className="w-4 h-4" aria-hidden="true" /> Descargar PDF
                  </Button>
                  <Button
                    onClick={onPreviewPdf}
                    variant="outline"
                    size="md"
                    aria-label="Previsualizar el PDF de la carta de presentación"
                  >
                    <Eye className="w-4 h-4" aria-hidden="true" /> Ver PDF
                  </Button>
                </>
              ) : (
                <Button variant="primary" size="md" disabled>
                  <FileText className="w-4 h-4" /> PDF no disponible
                </Button>
              )}
              <Button onClick={onCopy} variant="outline" size="md">
                {copied ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
                {copied ? 'Copiada' : 'Copiar carta'}
              </Button>
              <Button onClick={onDownload} variant="outline" size="md">
                <FileText className="w-4 h-4" /> Descargar .txt
              </Button>
              <Button onClick={onRegenerate} variant="warning" size="md">
                <RefreshCw className="w-4 h-4" /> Generar otra versión
              </Button>
            </div>

            <p className="text-xs text-muted-foreground mt-4 flex items-start gap-1.5">
              <FileText className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              Revisala antes de enviarla: la carta usa únicamente los datos de tu
              CV, pero el tono y los énfasis son edición tuya.
            </p>
          </Card>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default CoverLetterPanel;
