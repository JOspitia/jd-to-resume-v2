/**
 * yamlFormData — T2 of feat/yaml-editor-structured
 *
 * Structured form data for the YAML editor. The user edits fields, not
 * YAML text. This module owns:
 *   - The TypeScript types (form data shape).
 *   - parseYamlToFormData(yamlText) — YAML string -> structured object.
 *   - serializeFormDataToYaml(form) — structured object -> YAML string.
 *
 * The round-trip must be lossless for the structures the backend actually
 * emits: empty strings render as '', empty arrays render as [], the
 * summary uses YAML literal-block style (|) when it contains a newline.
 */

import yaml from 'js-yaml';

// ---------------------------------------------------------------------------
// Types — mirror the GeminiResumeOutput Pydantic schema in backend/main.py
// ---------------------------------------------------------------------------

export interface ContactInfo {
  name: string;
  location: string;
  phone: string;
  email: string;
  portfolio: string;
  linkedin: string;
  github: string;
}

export interface EducationEntry {
  school: string;
  degree: string;
  dates: string;
  gpa: string;
}

export interface ExperienceEntry {
  company: string;
  role: string;
  dates: string;
  points: string[];
}

export interface SkillCategory {
  category: string;
  items: string[];
}

export interface ProjectEntry {
  name: string;
  dates: string;
  points: string[];
}

export interface YamlFormData {
  contact: ContactInfo;
  summary: string;
  education: EducationEntry[];
  skills: SkillCategory[];
  experience: ExperienceEntry[];
  projects: ProjectEntry[];
  achievements: string[];
  section_labels: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Empty-state factory — the user can start from a blank profile or from a
// YAML the backend emitted.
// ---------------------------------------------------------------------------

export function emptyFormData(): YamlFormData {
  return {
    contact: {
      name: '',
      location: '',
      phone: '',
      email: '',
      portfolio: '',
      linkedin: '',
      github: '',
    },
    summary: '',
    education: [],
    skills: [],
    experience: [],
    projects: [],
    achievements: [],
    section_labels: {
      summary: 'Resumen Profesional',
      education: 'Educación',
      skills: 'Habilidades',
      experience: 'Experiencia Laboral',
      projects: 'Proyectos',
      achievements: 'Logros',
      portfolio: 'Portafolio',
    },
  };
}

// ---------------------------------------------------------------------------
// Parser — YAML string -> YamlFormData
//
// Tolerant of missing fields: anything not in the YAML becomes the empty
// state. This lets the user start editing a half-formed CV without crashes.
// ---------------------------------------------------------------------------

type RawYaml = Record<string, unknown>;

function asString(v: unknown): string {
  return typeof v === 'string' ? v : '';
}
function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : [];
}
function asRecord(v: unknown): RawYaml {
  return v && typeof v === 'object' && !Array.isArray(v)
    ? (v as RawYaml)
    : {};
}

// ---------------------------------------------------------------------------
// fixBullets — heuristic to split a pasted block of text into one bullet
// per logical line. Used by the "Fix format" button in the experience
// section of the form editor.
//
// Splitting strategy (tries each in order, returns the first that yields
// more than one item):
//   1. Split on blank lines (\n\n) — explicit paragraphs.
//   2. Split on single newlines (\n) — manual line breaks.
//   3. Split on sentence boundaries (". " before an uppercase letter) —
//      the most common case for users who paste a single dense paragraph
//      from their old CV.
// In every case, each item is trimmed and empty items are dropped.
// ---------------------------------------------------------------------------
export function fixBullets(text: string): string[] {
  if (!text || !text.trim()) return [];

  const trimmed = text.trim();

  // 1. Paragraphs
  let parts = trimmed.split(/\n\s*\n/).map((s) => s.trim()).filter((s) => s.length > 0);
  if (parts.length > 1) return parts;

  // 2. Manual line breaks
  parts = trimmed.split('\n').map((s) => s.trim()).filter((s) => s.length > 0);
  if (parts.length > 1) return parts;

  // 3. Sentence boundaries. Match ". " followed by a capital letter or
  //    a digit (so percentages like ". 20%" don't split). Keep the period
  //    attached to the preceding sentence.
  const sentenceRe = /\.\s+(?=[A-ZÁÉÍÓÚÑ0-9])/;
  parts = trimmed
    .split(sentenceRe)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map((s) => (s.endsWith('.') || s.endsWith(']') || s.endsWith('%') || s.endsWith(')')) ? s : s + '.');
  return parts;
}

// ---------------------------------------------------------------------------
// fixSummary — heuristic to format a pasted block as proper paragraphs.
// Used by the "Auto-formatear" button in the Resumen profesional section.
// Summary is a single string (not a list), so the goal is to ensure
// sensible paragraph separation, not to split into discrete bullets.
//
// Strategy:
//   1. If the text already has paragraph breaks (\n\n or more), normalize
//      them: trim each paragraph, drop empties, join with exactly \n\n.
//   2. If the text has single line breaks (\n), promote them to paragraph
//      breaks and trim.
//   3. If the text is a single block, split into sentences and group 2
//      sentences per paragraph.
// In every case, collapse internal whitespace runs to single spaces so
// the output reads cleanly.
// ---------------------------------------------------------------------------
export function fixSummary(text: string): string {
  if (!text || !text.trim()) return text;

  const trimmed = text.replace(/[ \t]+\n/g, '\n').trim();

  // 1. Already has paragraph breaks — normalize.
  if (/\n\s*\n/.test(trimmed)) {
    return trimmed
      .split(/\n\s*\n+/)
      .map((p) => p.replace(/\s+/g, ' ').trim())
      .filter((p) => p.length > 0)
      .join('\n\n');
  }

  // 2. Has single newlines — promote to paragraph breaks.
  if (trimmed.includes('\n')) {
    return trimmed
      .split(/\n+/)
      .map((p) => p.replace(/\s+/g, ' ').trim())
      .filter((p) => p.length > 0)
      .join('\n\n');
  }

  // 3. Single block — split into sentences, group 2 per paragraph.
  const sentenceRe = /\.\s+(?=[A-ZÁÉÍÓÚÑ0-9])/;
  const sentences = trimmed
    .split(sentenceRe)
    .map((s) => s.replace(/\s+/g, ' ').trim())
    .filter((s) => s.length > 0)
    .map((s) => (s.endsWith('.') || s.endsWith(']') || s.endsWith('%') || s.endsWith(')')) ? s : s + '.');

  if (sentences.length <= 2) return sentences.join(' ');

  const paragraphs: string[] = [];
  for (let i = 0; i < sentences.length; i += 2) {
    paragraphs.push(sentences.slice(i, i + 2).join(' '));
  }
  return paragraphs.join('\n\n');
}

export function parseYamlToFormData(yamlText: string): YamlFormData {
  const empty = emptyFormData();
  let raw: RawYaml;
  try {
    const loaded = yaml.load(yamlText);
    raw = asRecord(loaded);
  } catch {
    return empty;
  }

  const sectionLabels = asRecord(raw['section_labels']);

  return {
    contact: {
      name: asString(raw['name']),
      location: asString(raw['location']),
      phone: asString(raw['phone']),
      email: asString(raw['email']),
      portfolio: asString(raw['portfolio']),
      linkedin: asString(raw['linkedin']),
      github: asString(raw['github']),
    },
    summary: asString(raw['summary']),
    education: Array.isArray(raw['education'])
      ? (raw['education'] as unknown[])
          .filter((e) => e && typeof e === 'object')
          .map((e) => {
            const r = asRecord(e);
            return {
              school: asString(r['school']),
              degree: asString(r['degree']),
              dates: asString(r['dates']),
              gpa: asString(r['gpa']),
            };
          })
      : [],
    skills: Array.isArray(raw['skills'])
      ? (raw['skills'] as unknown[])
          .filter((s) => s && typeof s === 'object')
          .map((s) => {
            const r = asRecord(s);
            return {
              category: asString(r['category']),
              items: asStringArray(r['items']),
            };
          })
      : [],
    experience: Array.isArray(raw['experience'])
      ? (raw['experience'] as unknown[])
          .filter((x) => x && typeof x === 'object')
          .map((x) => {
            const r = asRecord(x);
            return {
              company: asString(r['company']),
              role: asString(r['role']),
              dates: asString(r['dates']),
              points: asStringArray(r['points']),
            };
          })
      : [],
    projects: Array.isArray(raw['projects'])
      ? (raw['projects'] as unknown[])
          .filter((p) => p && typeof p === 'object')
          .map((p) => {
            const r = asRecord(p);
            return {
              name: asString(r['name']),
              dates: asString(r['dates']),
              points: asStringArray(r['points']),
            };
          })
      : [],
    achievements: asStringArray(raw['achievements']),
    section_labels: {
      summary: asString(sectionLabels['summary']) || empty.section_labels.summary,
      education: asString(sectionLabels['education']) || empty.section_labels.education,
      skills: asString(sectionLabels['skills']) || empty.section_labels.skills,
      experience: asString(sectionLabels['experience']) || empty.section_labels.experience,
      projects: asString(sectionLabels['projects']) || empty.section_labels.projects,
      achievements: asString(sectionLabels['achievements']) || empty.section_labels.achievements,
      portfolio: asString(sectionLabels['portfolio']) || empty.section_labels.portfolio,
    },
  };
}

// ---------------------------------------------------------------------------
// Serializer — YamlFormData -> YAML string
//
// Round-trip note: the backend reads the YAML with PyYAML safe_load, so
// any valid YAML it accepts must be reproduced here. We use the literal
// block style (|) for the summary because it preserves line breaks; the
// other strings are plain (no special chars in the user's CV, so we just
// quote them when they contain YAML control characters).
// ---------------------------------------------------------------------------

function yamlString(s: string): string {
  // Empty -> ''
  if (s === '') return "''";
  // If the string contains YAML control characters, quote it.
  if (/[:{}\[\],&*#?|<>=!%@`]/.test(s) || s !== s.trim()) {
    return JSON.stringify(s);
  }
  return s;
}

function yamlMultiline(s: string): string {
  if (s === '') return "''";
  if (!s.includes('\n')) return yamlString(s);
  // Use literal block style (|) — preserves newlines, no escape needed.
  // Indent the content by 2 spaces so the YAML parser reads it back
  // as a single string with newlines.
  const lines = s.split('\n');
  return '|\n' + lines.map((l) => '  ' + l).join('\n');
}

// Serialize a string field. Used for the simple `key: value` lines inside
// a list entry (e.g. `  school: Universidad X`).
function fieldLine(key: string, value: string): string {
  return `  ${key}: ${yamlString(value)}`;
}

// Serialize a list of strings under a key. Empty -> `key: []`,
// non-empty -> `key:\n  - item1\n  - item2`.
function stringListBlock(key: string, items: string[]): string[] {
  if (items.length === 0) return [`  ${key}: []`];
  // The key sits at 2-space indent (inside a `- ` list entry). The list
  // items must be nested one level deeper (4-space indent) for strict
  // YAML parsers like js-yaml. PyYAML is lenient and accepts 2-space
  // indent, but js-yaml raises 'bad indentation of a sequence entry'.
  return [`  ${key}:`, ...items.map((it) => `    - ${yamlString(it)}`)];
}

export function serializeFormDataToYaml(data: YamlFormData): string {
  const lines: string[] = [];

  // Contact (flat scalars)
  lines.push(`name: ${yamlString(data.contact.name)}`);
  lines.push(`location: ${yamlString(data.contact.location)}`);
  lines.push(`phone: ${yamlString(data.contact.phone)}`);
  lines.push(`email: ${yamlString(data.contact.email)}`);
  lines.push(`portfolio: ${yamlString(data.contact.portfolio)}`);
  lines.push(`linkedin: ${yamlString(data.contact.linkedin)}`);
  lines.push(`github: ${yamlString(data.contact.github)}`);
  lines.push('');

  // Summary (multiline)
  lines.push(`summary: ${yamlMultiline(data.summary)}`);
  lines.push('');

  // Education — list of objects {school, degree, dates, gpa}
  lines.push('education:');
  if (data.education.length === 0) {
    lines.push('[]');
  } else {
    for (const e of data.education) {
      lines.push(`- ${fieldLine('school', e.school)}`);
      lines.push(`  ${fieldLine('degree', e.degree)}`);
      lines.push(`  ${fieldLine('dates', e.dates)}`);
      lines.push(`  ${fieldLine('gpa', e.gpa)}`);
    }
  }
  lines.push('');

  // Skills — list of objects {category, items: string[]}
  lines.push('skills:');
  if (data.skills.length === 0) {
    lines.push('[]');
  } else {
    for (const s of data.skills) {
      lines.push(`- ${fieldLine('category', s.category)}`);
      lines.push(...stringListBlock('items', s.items));
    }
  }
  lines.push('');

  // Experience — list of objects {company, role, dates, points: string[]}
  lines.push('experience:');
  if (data.experience.length === 0) {
    lines.push('[]');
  } else {
    for (const x of data.experience) {
      lines.push(`- ${fieldLine('company', x.company)}`);
      lines.push(`  ${fieldLine('role', x.role)}`);
      lines.push(`  ${fieldLine('dates', x.dates)}`);
      lines.push(...stringListBlock('points', x.points));
    }
  }
  lines.push('');

  // Projects — list of objects {name, dates, points: string[]}
  lines.push('projects:');
  if (data.projects.length === 0) {
    lines.push('[]');
  } else {
    for (const p of data.projects) {
      lines.push(`- ${fieldLine('name', p.name)}`);
      lines.push(`  ${fieldLine('dates', p.dates)}`);
      lines.push(...stringListBlock('points', p.points));
    }
  }
  lines.push('');

  // Achievements — flat list of strings
  lines.push('achievements:');
  if (data.achievements.length === 0) {
    lines.push('[]');
  } else {
    for (const a of data.achievements) {
      lines.push(`- ${yamlString(a)}`);
    }
  }
  lines.push('');

  // Section labels — flat key/value map
  lines.push('section_labels:');
  for (const [k, v] of Object.entries(data.section_labels)) {
    lines.push(`  ${k}: ${yamlString(v)}`);
  }

  return lines.join('\n') + '\n';
}
