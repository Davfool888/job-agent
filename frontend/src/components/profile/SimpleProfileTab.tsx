import { DateInput, EntryCard } from "../../components/profile/fields";
import { SuggestInput } from "../../components/forms/SuggestInput";
import type {
  LanguageEntry,
  Profile,
  ProfileEntry,
} from "../../types/profile";

interface SimpleProfileTabProps {
  locked: boolean;
  current: Profile;
  set: (patch: Partial<Profile>) => void;
  saved: boolean;
  saveError: string | null;
  submit: (e: React.FormEvent) => Promise<void>;
  saving: boolean;
  titleOptions: string[];
  citySelectOptions: (value: string) => string[];
  locationValue: string;
  experiences: ProfileEntry[];
  setExperiences: (next: ProfileEntry[]) => void;
  education: ProfileEntry[];
  setEducation: (next: ProfileEntry[]) => void;
  languages: LanguageEntry[];
  setLanguages: (next: LanguageEntry[]) => void;
}

export function SimpleProfileTab({
  locked,
  current,
  set,
  saved,
  saveError,
  submit,
  saving,
  titleOptions,
  citySelectOptions,
  locationValue,
  experiences,
  setExperiences,
  education,
  setEducation,
  languages,
  setLanguages,
}: SimpleProfileTabProps) {
  const genId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

  return (
    <form className="card" onSubmit={submit}>
      {saveError && <div className="alert-error">{saveError}</div>}
      {saved && (
        <div className="alert-success">
          Perfil guardado en el backend.
        </div>
      )}
      <fieldset
        disabled={locked}
        style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
      >

      {/* INFORMACIÓN PERSONAL BÁSICA */}
      <h3 className="card-title">Información personal</h3>
      <div className="form-grid">
        <div className="field">
          <label>Nombre completo</label>
          <input className="input" value={current.full_name} onChange={(e) => set({ full_name: e.target.value })} />
        </div>
        <div className="field">
          <label>Título profesional</label>
          <SuggestInput
            value={current.title}
            onChange={(v) => set({ title: v })}
            options={titleOptions}
            placeholder="Elige de la lista: Analista de Datos"
            strict
          />
        </div>
        <div className="field">
          <label>Ubicación</label>
          <select
            className="select"
            value={locationValue}
            onChange={(e) => set({ location: e.target.value })}
          >
            <option value="">— Elige una ciudad —</option>
            {citySelectOptions(locationValue).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* INFORMACIÓN DE CONTACTO */}
      <h3 className="card-title" style={{ marginTop: 16 }}>
        Información de contacto
      </h3>
      <div className="form-grid">
        <div className="field">
          <label>Correo principal</label>
          <input className="input" type="email" value={current.email ?? ""} onChange={(e) => set({ email: e.target.value })} placeholder="usuario@ejemplo.com" />
        </div>
        <div className="field">
          <label>Correo secundario</label>
          <input className="input" type="email" value={current.secondary_email ?? ""} onChange={(e) => set({ secondary_email: e.target.value })} placeholder="opcional@ejemplo.com" />
        </div>
        <div className="field">
          <label>Celular principal</label>
          <input className="input" type="tel" value={current.phone ?? ""} onChange={(e) => set({ phone: e.target.value })} placeholder="+57 3XX XXX XXXX" />
        </div>
        <div className="field">
          <label>Celular de respaldo</label>
          <input className="input" type="tel" value={current.secondary_phone ?? ""} onChange={(e) => set({ secondary_phone: e.target.value })} placeholder="+57 3XX XXX XXXX" />
        </div>
        <div className="field">
          <label>LinkedIn</label>
          <input className="input" value={current.linkedin ?? ""} onChange={(e) => set({ linkedin: e.target.value })} placeholder="https://linkedin.com/in/usuario" />
        </div>
        <div className="field">
          <label>GitHub</label>
          <input className="input" value={current.github ?? ""} onChange={(e) => set({ github: e.target.value })} placeholder="https://github.com/usuario" />
        </div>
        <div className="field">
          <label>Portafolio</label>
          <input className="input" value={current.portfolio ?? ""} onChange={(e) => set({ portfolio: e.target.value })} placeholder="https://portafolio.com" />
        </div>
      </div>

      {/* EXPERIENCIA LABORAL - Solo descripción general */}
      <h3 className="card-title" style={{ marginTop: 16 }}>
        Experiencia laboral
      </h3>
      <p className="card-sub">Agrega tus experiencias laborales con descripción general. En el perfil estructurado podrás detallar tareas específicas por óptica.</p>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setExperiences([...experiences, { id: genId(), title: "", company: "", start_date: null, end_date: null, is_current: false, description: "", perspectives: [] }])} disabled={locked}>
          + Agregar experiencia
        </button>
      </div>
      {experiences.map((exp, idx) => (
        <EntryCard
          key={exp.id}
          title={exp.title || `Experiencia ${idx + 1}`}
          subtitle={exp.company}
          onRemove={() => setExperiences(experiences.filter((_, i) => i !== idx))}
          defaultOpen
        >
          <div className="form-grid">
            <div className="field">
              <label>Empresa</label>
              <input className="input" value={exp.company ?? ""} onChange={(evt) => setExperiences(experiences.map((item, i) => i === idx ? { ...item, company: evt.target.value } : item))} placeholder="Nombre de la empresa" />
            </div>
            <div className="field">
              <label>Cargo</label>
              <SuggestInput
                value={exp.title ?? ""}
                onChange={(v) => setExperiences(experiences.map((item, i) => i === idx ? { ...item, title: v } : item))}
                options={titleOptions}
                placeholder="Elige de la lista: Analista de Datos"
                strict
              />
            </div>
            <div className="field">
              <label>Fecha de inicio</label>
              <DateInput month value={exp.start_date ?? null} onChange={(v) => setExperiences(experiences.map((item, i) => i === idx ? { ...item, start_date: v } : item))} />
            </div>
            <div className="field">
              <label>Fecha de finalización</label>
              <DateInput month value={exp.is_current ? null : (exp.end_date ?? null)} onChange={(v) => setExperiences(experiences.map((item, i) => i === idx ? { ...item, end_date: v } : item))} />
            </div>
            <div className="field">
              <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={!!exp.is_current}
                  onChange={(evt) => setExperiences(experiences.map((item, i) => i === idx ? { ...item, is_current: evt.target.checked, end_date: evt.target.checked ? null : item.end_date } : item))}
                />
                Actualmente trabajo aquí
              </label>
            </div>
            <div className="field" style={{ gridColumn: "1 / -1" }}>
              <label>Descripción general</label>
              <textarea
                className="textarea"
                rows={3}
                value={exp.description ?? ""}
                onChange={(evt) => setExperiences(experiences.map((item, i) => i === idx ? { ...item, description: evt.target.value } : item))}
                placeholder="Describe tus responsabilidades y logros principales..."
              />
            </div>
          </div>
        </EntryCard>
      ))}

      {/* EDUCACIÓN - Solo descripción general */}
      <h3 className="card-title" style={{ marginTop: 16 }}>
        Educación
      </h3>
      <p className="card-sub">Agrega tu formación académica. En el perfil estructurado podrás detallar materias, proyectos y habilidades por óptica.</p>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setEducation([...education, { id: genId(), degree: "", institution: "", start_date: null, end_date: null, description: "", perspectives: [] }])} disabled={locked}>
          + Agregar educación
        </button>
      </div>
      {education.map((edu, idx) => (
        <EntryCard
          key={edu.id}
          title={edu.degree || `Educación ${idx + 1}`}
          subtitle={edu.institution}
          onRemove={() => setEducation(education.filter((_, i) => i !== idx))}
          defaultOpen
        >
          <div className="form-grid">
            <div className="field">
              <label>Institución</label>
              <input className="input" value={edu.institution ?? ""} onChange={(evt) => setEducation(education.map((item, i) => i === idx ? { ...item, institution: evt.target.value } : item))} placeholder="Universidad, instituto, etc." />
            </div>
            <div className="field">
              <label>Título / Programa</label>
              <input className="input" value={edu.degree ?? ""} onChange={(evt) => setEducation(education.map((item, i) => i === idx ? { ...item, degree: evt.target.value } : item))} placeholder="Ej: Ingeniería de Sistemas, Maestría en Data Science" />
            </div>
            <div className="field">
              <label>Fecha de inicio</label>
              <DateInput month value={edu.start_date ?? null} onChange={(v) => setEducation(education.map((item, i) => i === idx ? { ...item, start_date: v } : item))} />
            </div>
            <div className="field">
              <label>Fecha de finalización</label>
              <DateInput month value={edu.end_date ?? null} onChange={(v) => setEducation(education.map((item, i) => i === idx ? { ...item, end_date: v } : item))} />
            </div>
            <div className="field" style={{ gridColumn: "1 / -1" }}>
              <label>Descripción</label>
              <textarea
                className="textarea"
                rows={3}
                value={edu.description ?? ""}
                onChange={(evt) => setEducation(education.map((item, i) => i === idx ? { ...item, description: evt.target.value } : item))}
                placeholder="Materias relevantes, tesis, proyectos, honores..."
              />
            </div>
          </div>
        </EntryCard>
      ))}

      {/* IDIOMAS */}
      <h3 className="card-title" style={{ marginTop: 16 }}>
        Idiomas
      </h3>
      <p className="card-sub">Agrega los idiomas que conoces con nivel general. En el perfil estructurado podrás detallar por habilidad (listening, reading, writing, speaking).</p>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setLanguages([...languages, { id: genId(), language: null, language_label: "", academy: "", level: null, listening: null, reading: null, writing: null, speaking: null }])} disabled={locked}>
          + Agregar idioma
        </button>
      </div>
      {languages.map((lang, idx) => (
        <EntryCard
          key={lang.id}
          title={lang.language_label || lang.language || `Idioma ${idx + 1}`}
          subtitle={lang.academy}
          onRemove={() => setLanguages(languages.filter((_, i) => i !== idx))}
          defaultOpen
        >
          <div className="form-grid">
            <div className="field">
              <label>Idioma</label>
              <SuggestInput
                value={lang.language_label ?? ""}
                onChange={(v) => setLanguages(languages.map((l, i) => i === idx ? { ...l, language_label: v, language: v.toLowerCase() } : l))}
                options={["Español", "Inglés", "Portugués", "Francés", "Alemán", "Italiano", "Chino", "Japonés", "Otro"]}
                placeholder="Ej: Inglés"
              />
            </div>
            <div className="field">
              <label>Academia / Institución</label>
              <input className="input" value={lang.academy ?? ""} onChange={(e) => setLanguages(languages.map((l, i) => i === idx ? { ...l, academy: e.target.value } : l))} placeholder="Ej: British Council, Alianza Francesa, autodidacta" />
            </div>
            <div className="field">
              <label>Nivel general</label>
              <select className="select" value={lang.level ?? ""} onChange={(e) => setLanguages(languages.map((l, i) => i === idx ? { ...l, level: e.target.value || null } : l))}>
                <option value="">—</option>
                <option value="A1">A1 - Principiante</option>
                <option value="A2">A2 - Básico</option>
                <option value="B1">B1 - Intermedio</option>
                <option value="B2">B2 - Intermedio Alto</option>
                <option value="C1">C1 - Avanzado</option>
                <option value="C2">C2 - Experto</option>
                <option value="native">Nativo</option>
              </select>
            </div>
          </div>
        </EntryCard>
      ))}

      <button className="btn btn-primary" disabled={saving || locked} style={{ marginTop: 16 }}>
        {saving ? "Guardando…" : "Guardar perfil simple"}
      </button>
      </fieldset>
    </form>
  );
}