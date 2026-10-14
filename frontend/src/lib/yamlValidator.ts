/**
 * yamlValidator — local YAML syntax check used by the editor panel.
 * Mirror of the same helper in feat/yaml-editor-validation (the auto-cleanup
 * branch). Kept here so the form-based editor can show a green/red badge
 * and inline error with line/column when the user toggles to "Ver YAML".
 */
import yaml from 'js-yaml';

export type YamlValidationResult = {
  valid: boolean;
  error?: string;
  line?: number;
  column?: number;
  parsed?: unknown;
};

export function validateYaml(text: string): YamlValidationResult {
  if (!text || !text.trim()) {
    return { valid: false, error: 'El YAML está vacío.' };
  }
  try {
    const parsed = yaml.load(text);
    return { valid: true, parsed };
  } catch (e) {
    const err = e as { reason?: string; message?: string; mark?: { line?: number; column?: number } };
    const errorMessage = err.reason ?? err.message ?? 'Error de sintaxis YAML';
    return {
      valid: false,
      error: errorMessage,
      line: err.mark?.line,
      column: err.mark?.column,
    };
  }
}
