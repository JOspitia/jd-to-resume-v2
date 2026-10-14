// Minimal local type declarations for js-yaml (v4.x).
// Same shim as feat/yaml-editor-validation. Kept here so the form-based
// editor in this branch type-checks without adding @types/js-yaml.

declare module 'js-yaml' {
  export interface YAMLMark {
    line: number;
    column: number;
    position?: number;
    snippet?: string;
  }

  export class YAMLException extends Error {
    readonly reason: string;
    readonly mark: YAMLMark;
    constructor(reason?: string, mark?: YAMLMark);
  }

  export function load(input: string, options?: unknown): unknown;
  export function dump(input: unknown, options?: unknown): string;
}
