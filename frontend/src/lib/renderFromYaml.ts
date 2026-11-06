/**
 * Shared "render this YAML with this design" call.
 *
 * `/api/render-from-yaml` re-renders a parsed CV **without calling the LLM**:
 * the backend parses the YAML it receives and hands it straight to the
 * renderer. That makes it the right endpoint for every "same text, different
 * design" operation:
 *
 *   * the YAML editor ("render again" after a manual edit), and
 *   * the redesign panel ("change the template / accent, keep the text").
 *
 * Both flows need the same FormData assembly and the same error mapping, so
 * it lives here instead of being copy-pasted.
 */

import { apiUrl, fetchWithTimeout } from './api';

export type RenderFromYamlOptions = {
  /** The YAML document to render. */
  yaml: string;
  /** RenderCV theme id (`sb2nov`, `classic`, `moderncv`) or `classic_html`. */
  theme: string;
  /** Accent palette id (`none`, `navy`, `teal`, ...). */
  accent?: string;
  /** Tighten the layout so the CV fits on a single page. */
  fitSinglePage?: boolean;
  /** Insert a hard page break before this section. */
  pageBreakSection?: string;
  /** Job description — kept for parity with the generation endpoint. */
  jd?: string;
  /** Extra instructions — kept for parity with the generation endpoint. */
  customPrompt?: string;
  /** Domain game (`tech`, `hr_recruiting`, `psychology`). */
  domainGame?: string;
  /** Optional candidate photo, re-sent so the redesign keeps it. */
  photo?: File | null;
};

export type RenderFromYamlResult = {
  /** Absolute URL of the rendered PDF. */
  downloadUrl: string;
  /** Filename on disk (used as the base for later refinement passes). */
  filename: string;
};

/**
 * POST the YAML to `/api/render-from-yaml` and return the rendered PDF's
 * location.
 *
 * Throws an `Error` with a human-readable message when the backend rejects
 * the request or the render fails.
 */
export async function renderFromYaml(
  options: RenderFromYamlOptions,
): Promise<RenderFromYamlResult> {
  const {
    yaml,
    theme,
    accent,
    fitSinglePage,
    pageBreakSection,
    jd,
    customPrompt,
    domainGame,
    photo,
  } = options;

  const formData = new FormData();
  formData.append('yaml_content', yaml);
  formData.append('theme', theme);
  formData.append('accent', accent || 'none');
  formData.append('fit_single_page', fitSinglePage ? 'true' : 'false');
  if (pageBreakSection && pageBreakSection !== 'none') {
    formData.append('page_break_section', pageBreakSection);
  }
  if (jd) formData.append('jd', jd);
  if (customPrompt) formData.append('custom_instructions', customPrompt);
  if (domainGame) formData.append('domain_game', domainGame);
  // The photo is a presentation choice, not part of the YAML document, so it
  // is re-sent on every render pass.
  if (photo) formData.append('photo', photo);

  const res = await fetchWithTimeout(apiUrl('/api/render-from-yaml'), {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => '');
    throw new Error(
      `No se pudo aplicar el diseño (HTTP ${res.status})${errText ? `: ${errText}` : ''}`,
    );
  }

  const data = await res.json();
  if (data?.error) {
    throw new Error(data.error);
  }

  const downloadPath: string = data.download_url;
  const filename: string = data.filename || downloadPath.split('/').pop() || '';
  return { downloadUrl: apiUrl(downloadPath), filename };
}
