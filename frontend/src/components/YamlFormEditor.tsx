import { useRef } from 'react';
import { Plus, Trash2, Wand2 } from 'lucide-react';
import { fixBullets, fixSummary, type YamlFormData, type EducationEntry, type ExperienceEntry, type SkillCategory, type ProjectEntry } from '../lib/yamlFormData';

/**
 * YamlFormEditor — T2 of feat/yaml-editor-structured
 *
 * Structured form for editing the resume data. The user edits fields, not
 * raw YAML — no stray colons, no indentation accidents, no syntax errors.
 *
 * The component is fully controlled: the parent owns `formData` and
 * `onChange`. This component never mutates the parent's state directly;
 * every interaction calls `onChange(next)` with a new object.
 *
 * Layout: one section per top-level key, each in a card with add/remove
 * for lists. Same neo-brutalist `rm-box` aesthetic as the rest of the app.
 */

export type YamlFormEditorProps = {
  formData: YamlFormData;
  onChange: (next: YamlFormData) => void;
};

// ---------------------------------------------------------------------------
// Small reusable inputs
// ---------------------------------------------------------------------------

function Field({ label, children, span = 1 }: { label: string; children: React.ReactNode; span?: 1 | 2 }) {
  return (
    <label className={`flex flex-col gap-1 ${span === 2 ? 'sm:col-span-2' : ''}`}>
      <span className="text-[10px] font-mono uppercase tracking-wide text-gray-600">{label}</span>
      {children}
    </label>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: 'text' | 'email' | 'url' | 'tel';
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full border border-gray-400 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
    />
  );
}

function TextAreaInput({
  value,
  onChange,
  placeholder,
  rows = 3,
  inputRef,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  inputRef?: React.Ref<HTMLTextAreaElement>;
}) {
  return (
    <textarea
      ref={inputRef}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className="w-full border border-gray-400 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
    />
  );
}

function AddButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rm-btn bg-white border-2 border-black text-black text-xs px-3 py-1.5 font-bold flex items-center gap-1"
    >
      <Plus className="w-3.5 h-3.5" /> {label}
    </button>
  );
}

function RemoveButton({ onClick, label = 'Quitar' }: { onClick: () => void; label?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="rm-btn bg-rose-50 border-2 border-rose-700 text-rose-800 text-xs px-2 py-1 font-bold flex items-center gap-1"
    >
      <Trash2 className="w-3.5 h-3.5" /> {label}
    </button>
  );
}

function SectionCard({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="rm-box p-4 bg-white">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-bold font-serif uppercase tracking-wide">{title}</h4>
        {action}
      </div>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section: Contact
// ---------------------------------------------------------------------------

function ContactSection({
  data,
  onChange,
}: {
  data: YamlFormData['contact'];
  onChange: (next: YamlFormData['contact']) => void;
}) {
  const set = <K extends keyof YamlFormData['contact']>(k: K, v: string) =>
    onChange({ ...data, [k]: v });
  return (
    <SectionCard title="Datos de contacto">
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Nombre completo">
          <TextInput value={data.name} onChange={(v) => set('name', v)} placeholder="Juan Andrés Pérez Ocampo" />
        </Field>
        <Field label="Ubicación">
          <TextInput value={data.location} onChange={(v) => set('location', v)} placeholder="Ciudad, País" />
        </Field>
        <Field label="Teléfono">
          <TextInput type="tel" value={data.phone} onChange={(v) => set('phone', v)} placeholder="+00 000 000 0000" />
        </Field>
        <Field label="Email">
          <TextInput type="email" value={data.email} onChange={(v) => set('email', v)} placeholder="nombre@ejemplo.com" />
        </Field>
        <Field label="LinkedIn" span={2}>
          <TextInput type="url" value={data.linkedin} onChange={(v) => set('linkedin', v)} placeholder="https://linkedin.com/in/usuario" />
        </Field>
        <Field label="GitHub">
          <TextInput type="url" value={data.github} onChange={(v) => set('github', v)} placeholder="https://github.com/usuario" />
        </Field>
        <Field label="Portafolio">
          <TextInput type="url" value={data.portfolio} onChange={(v) => set('portfolio', v)} placeholder="https://miportafolio.com" />
        </Field>
      </div>
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// Section: Summary
// ---------------------------------------------------------------------------

function SummarySection({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLTextAreaElement>(null);

  const handleFix = () => {
    // Read the textarea's current DOM value (catches un-blurred edits).
    const text = ref.current?.value ?? value;
    onChange(fixSummary(text));
  };

  return (
    <SectionCard title="Resumen profesional">
      <TextAreaInput
        value={value}
        onChange={onChange}
        inputRef={ref}
        rows={5}
        placeholder="Ingeniero de Sistemas | Full-Stack Developer con +3 años construyendo aplicaciones web escalables con Python, React y Docker. Enfoque en clean code, testing y DevOps."
      />
      <div className="flex justify-between items-center -mt-1">
        <button
          type="button"
          onClick={handleFix}
          className="rm-btn bg-white border border-blue-700 text-blue-800 text-[10px] px-2 py-0.5 font-mono font-bold flex items-center gap-1 hover:bg-blue-50"
        >
          <Wand2 className="w-3 h-3" /> Auto-formatear
        </button>
        <span className="text-[10px] text-gray-500 italic">
          Separa un bloque pegado en párrafos (2 oraciones por párrafo)
        </span>
      </div>
      <p className="text-[10px] text-gray-500 mt-1">Soporta varias líneas. Se serializa como bloque literal (|) en YAML.</p>
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// Section: Education (list of cards)
// ---------------------------------------------------------------------------

function EducationSection({
  data,
  onChange,
}: {
  data: EducationEntry[];
  onChange: (next: EducationEntry[]) => void;
}) {
  const update = (i: number, patch: Partial<EducationEntry>) =>
    onChange(data.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));
  const remove = (i: number) => onChange(data.filter((_, idx) => idx !== i));
  const add = () => onChange([...data, { school: '', degree: '', dates: '', gpa: '' }]);

  return (
    <SectionCard
      title="Educación"
      action={<AddButton onClick={add} label="Agregar educación" />}
    >
      {data.length === 0 ? (
        <p className="text-xs text-gray-500 italic">Sin entradas. Click &ldquo;Agregar educación&rdquo; para empezar.</p>
      ) : (
        <div className="space-y-3">
          {data.map((e, i) => (
            <div key={i} className="border border-gray-300 p-3 space-y-2 bg-gray-50">
              <div className="grid sm:grid-cols-2 gap-2">
                <Field label="Institución">
                  <TextInput value={e.school} onChange={(v) => update(i, { school: v })} />
                </Field>
                <Field label="Título">
                  <TextInput value={e.degree} onChange={(v) => update(i, { degree: v })} />
                </Field>
                <Field label="Fechas">
                  <TextInput value={e.dates} onChange={(v) => update(i, { dates: v })} placeholder="2018-02 - 2024-01" />
                </Field>
                <Field label="GPA / Nota">
                  <TextInput value={e.gpa} onChange={(v) => update(i, { gpa: v })} />
                </Field>
              </div>
              <div className="flex justify-end">
                <RemoveButton onClick={() => remove(i)} />
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// Section: Skills (categories with items)
// ---------------------------------------------------------------------------

function SkillsSection({
  data,
  onChange,
}: {
  data: SkillCategory[];
  onChange: (next: SkillCategory[]) => void;
}) {
  const update = (i: number, patch: Partial<SkillCategory>) =>
    onChange(data.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  const updateItems = (i: number, itemsText: string) => {
    // Items are stored as a string[] (one entry per line in the textarea).
    const items = itemsText
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
    update(i, { items });
  };
  const itemsToText = (items: string[]) => items.join('\n');
  const remove = (i: number) => onChange(data.filter((_, idx) => idx !== i));
  const add = () => onChange([...data, { category: '', items: [] }]);

  return (
    <SectionCard
      title="Habilidades"
      action={<AddButton onClick={add} label="Agregar categoría" />}
    >
      {data.length === 0 ? (
        <p className="text-xs text-gray-500 italic">Sin categorías. Click &ldquo;Agregar categoría&rdquo; para empezar.</p>
      ) : (
        <div className="space-y-3">
          {data.map((s, i) => (
            <div key={i} className="border border-gray-300 p-3 space-y-2 bg-gray-50">
              <Field label="Nombre de la categoría">
                <TextInput
                  value={s.category}
                  onChange={(v) => update(i, { category: v })}
                  placeholder="Backend & APIs"
                />
              </Field>
              <Field label="Items (uno por línea)">
                <TextAreaInput
                  value={itemsToText(s.items)}
                  onChange={(v) => updateItems(i, v)}
                  rows={4}
                  placeholder={'Python & FastAPI\nReact & TypeScript\nPostgreSQL & Docker\nCI/CD con GitHub Actions'}
                />
              </Field>
              <div className="flex justify-end">
                <RemoveButton onClick={() => remove(i)} />
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// Mini-component: bullets textarea + "Auto-separar" button.
// Extracted so each experience entry gets its own useRef without violating
// the rules of hooks (a ref must not be created inside .map()).
// ---------------------------------------------------------------------------
function BulletTextarea({
  points,
  onChange,
}: {
  points: string[];
  onChange: (next: string[]) => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  const handleFix = () => {
    // Read the textarea's current DOM value (even if the user hasn't
    // blurred yet — React batches onChange commits, so props.points may
    // be stale). Falls back to the committed array.
    const text = ref.current?.value ?? points.join('\n');
    const fixed = fixBullets(text);
    onChange(fixed);
  };

  return (
    <>
      <Field label="Bullets (uno por línea)">
        <TextAreaInput
          value={points.join('\n')}
          onChange={(v) =>
            onChange(
              v
                .split('\n')
                .map((l) => l.trim())
                .filter((l) => l.length > 0),
            )
          }
          inputRef={ref}
          rows={5}
          placeholder={'Desarrollé APIs REST con FastAPI y PostgreSQL atendiendo +50 req/s con tiempo de respuesta <100ms. Reduje el time-to-deploy en 60% con pipeline CI/CD en GitHub Actions.'}
        />
      </Field>
      <div className="flex justify-between items-center -mt-1">
        <button
          type="button"
          onClick={handleFix}
          className="rm-btn bg-white border border-blue-700 text-blue-800 text-[10px] px-2 py-0.5 font-mono font-bold flex items-center gap-1 hover:bg-blue-50"
        >
          <Wand2 className="w-3 h-3" /> Auto-separar bullets
        </button>
        <span className="text-[10px] text-gray-500 italic">
          Separa un bloque pegado en bullets por párrafo u oración
        </span>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Section: Experience (cards with points sub-list)
// ---------------------------------------------------------------------------

function ExperienceSection({
  data,
  onChange,
}: {
  data: ExperienceEntry[];
  onChange: (next: ExperienceEntry[]) => void;
}) {
  const update = (i: number, patch: Partial<ExperienceEntry>) =>
    onChange(data.map((x, idx) => (idx === i ? { ...x, ...patch } : x)));
  const remove = (i: number) => onChange(data.filter((_, idx) => idx !== i));
  const add = () =>
    onChange([...data, { company: '', role: '', dates: '', points: [] }]);

  return (
    <SectionCard
      title="Experiencia laboral"
      action={<AddButton onClick={add} label="Agregar experiencia" />}
    >
      {data.length === 0 ? (
        <p className="text-xs text-gray-500 italic">Sin experiencias. Click &ldquo;Agregar experiencia&rdquo; para empezar.</p>
      ) : (
        <div className="space-y-3">
          {data.map((x, i) => (
            <div key={i} className="border border-gray-300 p-3 space-y-2 bg-gray-50">
              <div className="grid sm:grid-cols-2 gap-2">
                <Field label="Empresa">
                  <TextInput value={x.company} onChange={(v) => update(i, { company: v })} />
                </Field>
                <Field label="Cargo">
                  <TextInput value={x.role} onChange={(v) => update(i, { role: v })} />
                </Field>
                <Field label="Fechas" span={2}>
                  <TextInput value={x.dates} onChange={(v) => update(i, { dates: v })} placeholder="2025-02 - 2026-06" />
                </Field>
              </div>
              <BulletTextarea
                points={x.points}
                onChange={(p) => update(i, { points: p })}
              />
              <div className="flex justify-end">
                <RemoveButton onClick={() => remove(i)} />
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// Section: Projects (smaller list, same pattern as Experience without points sub-list detail)
// ---------------------------------------------------------------------------

function ProjectsSection({
  data,
  onChange,
}: {
  data: ProjectEntry[];
  onChange: (next: ProjectEntry[]) => void;
}) {
  const update = (i: number, patch: Partial<ProjectEntry>) =>
    onChange(data.map((p, idx) => (idx === i ? { ...p, ...patch } : p)));
  const updatePoints = (i: number, pointsText: string) => {
    const points = pointsText
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
    update(i, { points });
  };
  const remove = (i: number) => onChange(data.filter((_, idx) => idx !== i));
  const add = () => onChange([...data, { name: '', dates: '', points: [] }]);

  return (
    <SectionCard
      title="Proyectos"
      action={<AddButton onClick={add} label="Agregar proyecto" />}
    >
      {data.length === 0 ? (
        <p className="text-xs text-gray-500 italic">Sin proyectos. (Opcional)</p>
      ) : (
        <div className="space-y-3">
          {data.map((p, i) => (
            <div key={i} className="border border-gray-300 p-3 space-y-2 bg-gray-50">
              <div className="grid sm:grid-cols-2 gap-2">
                <Field label="Nombre">
                  <TextInput value={p.name} onChange={(v) => update(i, { name: v })} />
                </Field>
                <Field label="Fechas">
                  <TextInput value={p.dates} onChange={(v) => update(i, { dates: v })} />
                </Field>
              </div>
              <Field label="Bullets (uno por línea)">
                <TextAreaInput
                  value={p.points.join('\n')}
                  onChange={(v) => updatePoints(i, v)}
                  rows={3}
                />
              </Field>
              <div className="flex justify-end">
                <RemoveButton onClick={() => remove(i)} />
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// Section: Achievements (simple string list)
// ---------------------------------------------------------------------------

function AchievementsSection({
  data,
  onChange,
}: {
  data: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <SectionCard
      title="Logros"
      action={
        <AddButton
          onClick={() => onChange([...data, ''])}
          label="Agregar logro"
        />
      }
    >
      {data.length === 0 ? (
        <p className="text-xs text-gray-500 italic">Sin logros. (Opcional)</p>
      ) : (
        <div className="space-y-2">
          {data.map((a, i) => (
            <div key={i} className="flex gap-2 items-start">
              <textarea
                value={a}
                onChange={(e) => onChange(data.map((x, idx) => (idx === i ? e.target.value : x)))}
                rows={2}
                className="flex-1 border border-gray-400 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
              />
              <RemoveButton onClick={() => onChange(data.filter((_, idx) => idx !== i))} />
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function YamlFormEditor({ formData, onChange }: YamlFormEditorProps) {
  return (
    <div className="space-y-4">
      <ContactSection
        data={formData.contact}
        onChange={(c) => onChange({ ...formData, contact: c })}
      />
      <SummarySection
        value={formData.summary}
        onChange={(v) => onChange({ ...formData, summary: v })}
      />
      <EducationSection
        data={formData.education}
        onChange={(e) => onChange({ ...formData, education: e })}
      />
      <ExperienceSection
        data={formData.experience}
        onChange={(e) => onChange({ ...formData, experience: e })}
      />
      <SkillsSection
        data={formData.skills}
        onChange={(s) => onChange({ ...formData, skills: s })}
      />
      <ProjectsSection
        data={formData.projects}
        onChange={(p) => onChange({ ...formData, projects: p })}
      />
      <AchievementsSection
        data={formData.achievements}
        onChange={(a) => onChange({ ...formData, achievements: a })}
      />
    </div>
  );
}

export default YamlFormEditor;
