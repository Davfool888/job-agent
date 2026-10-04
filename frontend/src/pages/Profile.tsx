import { useEffect, useState } from "react";
import { Header } from "../components/layout/Header";
import {
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import {
  Autocomplete,
  DateInput,
  EntryCard,
  TagInput,
} from "../components/profile/fields";
import { useAuth } from "../context/AuthContext";
import { useProfile } from "../hooks/useApi";
import { ADMIN_EMAIL } from "../lib/firebase";
import { SuggestInput } from "../components/forms/SuggestInput";
import {
  fetchCatalogs,
  fetchFullProfile,
  saveFullProfile,
} from "../services/profile";
import { COLOMBIAN_CITIES } from "../utils/cities";
import { SKILLS } from "../utils/skills";
import { TITLES } from "../utils/titles";
import {
  DOMAIN_SUGGESTIONS,
  ENTRY_STATUS_FALLBACK,
  MODALITY_FALLBACK,
  SOFT_SKILLS_FALLBACK,
  TITLE_CATEGORY_SUGGESTIONS,
  canonicalLocation,
  resolveOptionId,
} from "../utils/profileOptions";
import type {
  CatalogItem,
  Catalogs,
  CityRef,
  LanguageEntry,
  Profile,
  ProfileEntry,
  RichProfile,
} from "../types/profile";
import { EMPTY_PROFILE } from "../types/profile";

// True si la sesion actual es la cuenta administradora (unica que ve
// el perfil base global). Cualquier otra sesion solo puede ver scope
// own/demo; con scope compartido el frontend no muestra nada.
function useIsAdminSession(): boolean {
  const { firebaseUser, isGuest } = useAuth();
  if (!firebaseUser || isGuest) return false;
  return (firebaseUser.email ?? "").trim().toLowerCase() === ADMIN_EMAIL;
}

export function ProfilePage() {
  const { data, loading, error, reload, save, saving } = useProfile();
  const { catalogs } = useCatalogs();
  const { firebaseUser } = useAuth();
  const isAdmin = useIsAdminSession();
  const [form, setForm] = useState<Profile | null>(null);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  
  // Simple profile state (shared between tabs)
  const [simpleExperiences, setSimpleExperiences] = useState<ProfileEntry[]>(() => {
    // Initialize from current data if available
    return (current as any)?.experiences || [];
  });
  const [simpleEducation, setSimpleEducation] = useState<ProfileEntry[]>(() => {
    return (current as any)?.education || [];
  });
  const [simpleLanguages, setSimpleLanguages] = useState<LanguageEntry[]>(() => {
    return (current as any)?.languages || [];
  });

  if (loading) {
    return (
      <>
        <Header title="Perfil profesional" />
        <div className="content">
          <LoadingState label="Cargando perfil…" />
        </div>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <Header title="Perfil profesional" />
        <div className="content">
          <ErrorState message={error ?? "Error"} onRetry={reload} />
        </div>
      </>
    );
  }

  // Blindaje: con sesion no-admin, si el backend devolvio perfil
  // compartido (sin verificacion) no se muestra ni se edita nada.
  const locked =
    !!data &&
    !!firebaseUser &&
    !isAdmin &&
    data.scope !== "own" &&
    data.scope !== "demo";
  const current = locked ? { ...EMPTY_PROFILE } : (form ?? data);

  const titleOptions =
    catalogs?.professional_titles.map((t) => t.label) ?? TITLES;
  const cityOptions = catalogs?.cities.map((c) => c.label) ?? COLOMBIAN_CITIES;

  const locationValue = canonicalLocation(current.location, cityOptions);

  // Opciones de ciudad garantizando que el valor guardado siempre aparece
  // (aunque sea texto libre legacy que ya no esta en el catalogo).
  const citySelectOptions = (value: string) =>
    value && !cityOptions.includes(value)
      ? [...cityOptions, value]
      : cityOptions;

  const set = (patch: Partial<Profile>) => {
    if (locked) return;
    setForm({ ...current, ...patch });
    setSaved(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (locked) {
      setSaveError("Sesión sin acceso a este perfil.");
      return;
    }
    setSaveError(null);
    try {
      const updated = await save(current);
      setForm(updated);
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Error inesperado");
    } finally {
      // noop
    }
  };

  // Tab state
  const [activeTab, setActiveTab] = useState<"simple" | "structured">("simple");

  return (
    <>
      <Header
        title="Perfil profesional"
        subtitle="Fuente estructurada para matching, CV y análisis (PUT /profile y /profile/full)"
      />
      <div className="content">
        {locked && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>
              🔒 Esta sesión no tiene acceso al perfil mostrado por el
              servidor. No se muestra ni se puede editar nada hasta
              verificar la sesión.
            </p>
          </div>
        )}
        {data.scope === "own" && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>
              👤 Este es <strong>tu perfil personal</strong>: empieza en
              blanco y solo se llena con lo que guardes aquí. El perfil
              base de la cuenta principal no es visible para ti.
            </p>
          </div>
        )}
        {data.scope === "demo" && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>
              🧪 Estás viendo <strong>datos de prueba</strong> del modo
              invitado. Puedes editarlos libremente para testear; no
              afectan al perfil real.
            </p>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)", marginBottom: 16 }}>
            <button
              type="button"
              className={`btn btn-sm ${activeTab === "simple" ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setActiveTab("simple")}
              disabled={locked}
              style={{ padding: "8px 16px" }}
            >
              Perfil Simple
            </button>
            <button
              type="button"
              className={`btn btn-sm ${activeTab === "structured" ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setActiveTab("structured")}
              disabled={locked}
              style={{ padding: "8px 16px" }}
            >
              Perfil Estructurado
            </button>
          </div>
          <p className="card-sub" style={{ marginBottom: 0 }}>
            {activeTab === "simple"
              ? "Información básica de contacto, experiencia laboral, educación e idiomas (descripción general)."
              : "Perspectivas detalladas por experiencia/educación: tareas específicas, habilidades y herramientas por óptica (Data Analytics, Software, Finanzas, etc.)."}
          </p>
        </div>

        {activeTab === "simple" && (
          <SimpleProfileTab
            locked={locked}
            current={current}
            set={set}
            saved={saved}
            saveError={saveError}
            submit={submit}
            saving={saving}
            titleOptions={titleOptions}
            citySelectOptions={citySelectOptions}
            locationValue={locationValue}
            // Lifted state
            experiences={simpleExperiences}
            setExperiences={setSimpleExperiences}
            education={simpleEducation}
            setEducation={setSimpleEducation}
            languages={simpleLanguages}
            setLanguages={setSimpleLanguages}
          />
        )}

        {activeTab === "structured" && (
          <StructuredProfileManager 
            locked={locked} 
            simpleExperiences={simpleExperiences}
            simpleEducation={simpleEducation}
            simpleLanguages={simpleLanguages}
          />
        )}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Perfil estructurado: contacto, bloques administrables, idiomas, skills.
// ---------------------------------------------------------------------------

function useCatalogs() {
  const [catalogs, setCatalogs] = useState<Catalogs | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fetchCatalogs()
      .then((c) => alive && setCatalogs(c))
      .catch((e: unknown) =>
        alive && setError(e instanceof Error ? e.message : "Error"),
      );
    return () => {
      alive = false;
    };
  }, []);
  return { catalogs, error };
}

// ============================================================================
// PERFIL SIMPLE: Contacto básico, Experiencia, Educación, Idiomas (general)
// ============================================================================

function SimpleProfileTab({
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
  // Lifted state from ProfilePage
  experiences,
  setExperiences,
  education,
  setEducation,
  languages,
  setLanguages,
}: {
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
}) {
  // Función para generar ID único
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

type SectionKey = "experience" | "education" | "projects" | "certifications";

const SECTIONS: Array<{ key: SectionKey; label: string }> = [
  { key: "experience", label: "Experiencia laboral" },
  { key: "education", label: "Educación" },
  { key: "projects", label: "Proyectos" },
  { key: "certifications", label: "Certificaciones" },
];

function StructuredProfileManager({ 
  locked, 
  simpleExperiences,
  simpleEducation,
  simpleLanguages,
}: { 
  locked: boolean; 
  simpleExperiences: ProfileEntry[];
  simpleEducation: ProfileEntry[];
  simpleLanguages: LanguageEntry[];
}) {
  const { catalogs, error: catalogError } = useCatalogs();
  const { firebaseUser } = useAuth();
  const isAdmin = useIsAdminSession();
  const [rich, setRich] = useState<RichProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lockedRich, setLockedRich] = useState(false);
  const [section, setSection] = useState<SectionKey>("experience");
  const [saving, setSaving] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    setLockedRich(false);
    try {
      const data = await fetchFullProfile();
      if (
        firebaseUser &&
        !isAdmin &&
        data.scope !== "own" &&
        data.scope !== "demo"
      ) {
        setLockedRich(true);
        setRich(null);
        return;
      }
      
      // Merge with simple profile data for experience/education
      let mergedData = {
        ...data,
        technical_skills: data.technical_skills ?? [],
        soft_skills: data.soft_skills ?? [],
        years_experience: data.years_experience ?? null,
      };
      
      // If we have simple profile data, use its experience/education as base
      if (simpleExperiences.length > 0) {
        const richExperiences = mergedData.experience || [];
        const mergedExperiences = simpleExperiences.map((simpleExp: any, idx: number) => {
          const richExp = richExperiences[idx];
          if (richExp) {
            // Keep rich profile's perspectives and structured fields, but update base fields from simple
            return {
              ...richExp,
              company: simpleExp.company || richExp.company,
              title: simpleExp.title || richExp.title,
              start_date: simpleExp.start_date || richExp.start_date,
              end_date: simpleExp.end_date || richExp.end_date,
              is_current: simpleExp.is_current ?? richExp.is_current,
              description: simpleExp.description || richExp.description,
            };
          }
          // New entry from simple profile, add empty perspectives
          return {
            ...simpleExp,
            perspectives: [],
          };
        });
        mergedData.experience = mergedExperiences;
      }
      
      // Merge education similarly
      if (simpleEducation.length > 0) {
        const richEducation = mergedData.education || [];
        const mergedEducation = simpleEducation.map((simpleEdu: any, idx: number) => {
          const richEdu = richEducation[idx];
          if (richEdu) {
            return {
              ...richEdu,
              institution: simpleEdu.institution || richEdu.institution,
              degree: simpleEdu.degree || richEdu.degree,
              start_date: simpleEdu.start_date || richEdu.start_date,
              end_date: simpleEdu.end_date || richEdu.end_date,
              description: simpleEdu.description || richEdu.description,
            };
          }
          return {
            ...simpleEdu,
            perspectives: [],
          };
        });
        mergedData.education = mergedEducation;
      }
      
      // Merge languages if provided
      if (simpleLanguages.length > 0) {
        mergedData.languages = simpleLanguages;
      }
      
      setRich(mergedData);
      setWarnings(data._warnings ?? []);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Error inesperado");
    } finally {
      setLoading(false);
    }
  };

  const update = (next: RichProfile) => {
    setRich(next);
    setSaved(false);
  };

  const patchPersonal = (patch: Record<string, string>) => {
    if (!rich) return;
    update({ ...rich, personal: { ...rich.personal, ...patch } });
  };

  const entries = (rich?.[section] ?? []) as ProfileEntry[];
  const setEntries = (next: ProfileEntry[]) => {
    if (!rich) return;
    update({ ...rich, [section]: next });
  };
  const patchEntry = (i: number, patch: Partial<ProfileEntry>) =>
    setEntries(entries.map((e, j) => (j === i ? { ...e, ...patch } : e)));

  const submit = async () => {
    if (!rich || locked || lockedRich) return;
    setSaving(true);
    setSaveError(null);
    try {
      const out = await saveFullProfile(rich);
      setRich({ ...out.profile, _warnings: out.warnings } as RichProfile);
      setWarnings(out.warnings);
      setSaved(true);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Error inesperado");
    } finally {
      setSaving(false);
    }
  };

  const personal = rich?.personal ?? {};

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 className="card-title">Perfil Estructurado</h3>
      <p className="card-sub">
        Extiende el <strong>Perfil Simple</strong> añadiendo <strong>perspectivas</strong> a tus experiencias y educación.
        Cada perspectiva describe tareas específicas, skills y herramientas para una óptica distinta
        (ej: Data Analytics, Ingeniería de Software, Finanzas). La información base (empresa, cargo, fechas, descripción general)
        viene del Perfil Simple y no se duplica aquí.
      </p>
      {(locked || lockedRich) && (
        <div className="alert-error">
          🔒 Esta sesión no tiene acceso a este perfil estructurado.
        </div>
      )}
      {!locked && !lockedRich && !rich && !loading && (
        <button className="btn btn-ghost btn-sm" onClick={load}>
          Cargar perfil estructurado
        </button>
      )}
      {loading && <LoadingState label="Cargando perfil estructurado…" />}
      {loadError && <ErrorState message={loadError} onRetry={load} />}
      {catalogError && (
        <div className="alert-error">
          No se pudieron cargar los catálogos: {catalogError}
        </div>
      )}
      {rich && (
        <>
          {warnings.length > 0 && (
            <div className="alert-error">
              <p style={{ margin: "0 0 6px" }}>
                <strong>Advertencias de validación:</strong>
              </p>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <h4 style={{ margin: "12px 0 8px" }}>Información personal (viene del Perfil Simple)</h4>
          <div className="form-grid">
            <div className="field">
              <label>Nombre</label>
              <input
                className="input"
                value={personal.first_name ?? ""}
                onChange={(e) => patchPersonal({ first_name: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Apellido</label>
              <input
                className="input"
                value={personal.last_name ?? ""}
                onChange={(e) => patchPersonal({ last_name: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Título profesional</label>
              {catalogs ? (
                <Autocomplete
                  value={personal.title_id ?? ""}
                  onChange={(id) => patchPersonal({ title_id: id })}
                  options={catalogs.professional_titles.map((t) => ({
                    id: t.id,
                    label: t.label,
                  }))}
                  placeholder="Escribe para buscar…"
                  allowCustom
                  customLabel="Otro"
                />
              ) : (
                <input
                  className="input"
                  value={personal.title_label ?? personal.title ?? ""}
                  disabled
                  placeholder="Cargando catálogos…"
                  title="Espera a que carguen los catálogos para elegir sin errores"
                />
              )}
            </div>
            <div className="field">
              <label>Años de experiencia</label>
              <input
                className="input"
                type="number"
                min={0}
                max={60}
                step={0.5}
                value={rich.years_experience ?? ""}
                onChange={(e) =>
                  update({
                    ...rich,
                    years_experience:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
                placeholder="Ej: 2.5"
              />
            </div>
          </div>

          <h4 style={{ margin: "12px 0 8px" }}>Contacto (viene del Perfil Simple)</h4>
          <div className="form-grid">
            {(
              [
                ["email", "Correo principal"],
                ["secondary_email", "Correo secundario"],
                ["phone", "Celular principal"],
                ["secondary_phone", "Celular de respaldo"],
                ["linkedin", "LinkedIn"],
                ["github", "GitHub"],
                ["portfolio", "Portafolio"],
                ["address", "Dirección de residencia"],
              ] as Array<[string, string]>
            ).map(([key, label]) => (
              <div className="field" key={key}>
                <label>{label}</label>
                <input
                  className="input"
                  value={personal[key] ?? ""}
                  onChange={(e) => patchPersonal({ [key]: e.target.value })}
                />
              </div>
            ))}
          </div>

          <h4 style={{ margin: "12px 0 8px" }}>Ubicación preferida</h4>
          <div className="form-grid">
            <div className="field">
              <label>Ciudad / País</label>
              {catalogs ? (
                <Autocomplete
                  value={rich.personal.preferred_city_id ?? ""}
                  onChange={(id) =>
                    update({
                      ...rich,
                      personal: { ...rich.personal, preferred_city_id: id },
                    })
                  }
                  options={(catalogs.cities ?? []).map((c) => ({
                    id: c.id,
                    label: c.label,
                    hint: c.country,
                  }))}
                  placeholder="Ej: Bogotá"
                />
              ) : (
                <input
                  className="input"
                  value={rich.personal.preferred_location ?? ""}
                  disabled
                  placeholder="Cargando catálogos…"
                  title="Espera a que carguen los catálogos para elegir sin errores"
                />
              )}
            </div>
            <div className="field">
              <label>Modalidad preferida</label>
              <select
                className="select"
                value={rich.personal.preferred_modality ?? ""}
                onChange={(e) =>
                  update({
                    ...rich,
                    personal: {
                      ...rich.personal,
                      preferred_modality: e.target.value,
                    },
                  })
                }
              >
                <option value="">—</option>
                {((catalogs?.modalities ?? []) as CatalogItem[]).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <h4 style={{ margin: "12px 0 8px" }}>Skills globales</h4>
          <div className="form-grid">
            <div className="field">
              <label>Skills técnicas generales</label>
              <TagInput
                value={rich.technical_skills ?? []}
                onChange={(next) => update({ ...rich, technical_skills: next })}
                suggestions={SKILLS}
                placeholder="Escribe para buscar skill y Enter"
              />
            </div>
            <div className="field">
              <label>Skills blandas generales</label>
              <TagInput
                value={rich.soft_skills ?? []}
                onChange={(next) => update({ ...rich, soft_skills: next })}
                suggestions={SOFT_SKILLS_FALLBACK}
                placeholder="Escribe para buscar skill y Enter"
              />
            </div>
          </div>

          <h4 style={{ margin: "12px 0 8px" }}>Idiomas</h4>
          <LanguageManager
            languages={rich.languages ?? []}
            catalogs={catalogs}
            onChange={(languages) => update({ ...rich, languages })}
          />

          <h4 style={{ margin: "12px 0 8px" }}>Experiencia, educación, proyectos y certificaciones</h4>
          <p className="card-sub" style={{ marginBottom: 12 }}>
            <strong>Experiencia y Educación:</strong> La información base (empresa/institución, cargo/título, fechas, descripción general)
            proviene del <strong>Perfil Simple</strong>. Aquí solo añades <strong>perspectivas</strong> con tareas específicas,
            skills y herramientas por óptica profesional. Los botones "Agregar entrada" crean entradas vacías solo para
            proyectos/certificaciones; para experiencia/educación usa el Perfil Simple.
          </p>
          <div className="toolbar-row" style={{ marginBottom: 12 }}>
            {SECTIONS.map((s) => (
              <button
                key={s.key}
                type="button"
                className={`btn btn-sm ${section === s.key ? "btn-primary" : "btn-ghost"}`}
                onClick={() => setSection(s.key)}
                disabled={locked}
              >
                {s.label} ({((rich[s.key] ?? []) as ProfileEntry[]).length})
              </button>
            ))}
          </div>
          <EntrySection
            entries={entries}
            section={section}
            catalogs={catalogs}
            onPatch={patchEntry}
            onAdd={() => {
              // Solo permitir agregar entradas nuevas para projects y certifications
              // Para experience/education, se debe usar el Perfil Simple
              if (section === "projects") {
                setEntries([...entries, { name: "", perspectives: [] } as ProfileEntry]);
              } else if (section === "certifications") {
                setEntries([...entries, { name: "", perspectives: [] } as ProfileEntry]);
              }
            }}
            onRemove={(i) => setEntries(entries.filter((_, j) => j !== i))}
            isExperienceOrEducation={section === "experience" || section === "education"}
          />

          <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
            <button
              className="btn btn-primary btn-sm"
              disabled={saving}
              onClick={submit}
            >
              {saving ? "Guardando…" : "Guardar perfil estructurado"}
            </button>
            {saved && (
              <span style={{ color: "var(--success)", fontSize: 13 }}>
                Guardado.
              </span>
            )}
          </div>
          {saveError && (
            <div className="alert-error" style={{ marginTop: 8 }}>
              {saveError}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function LanguageManager({
  languages,
  catalogs,
  onChange,
}: {
  languages: LanguageEntry[];
  catalogs: Catalogs | null;
  onChange: (next: LanguageEntry[]) => void;
}) {
  const patch = (i: number, p: Partial<LanguageEntry>) =>
    onChange(languages.map((l, j) => (j === i ? { ...l, ...p } : l)));
  const levels = catalogs?.language_levels ?? [];
  return (
    <div>
      {languages.map((lang, i) => (
        <div
          key={lang.id || i}
          style={{
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: 10,
            marginBottom: 8,
          }}
        >
          <div className="form-grid">
            <div className="field">
              <label>Idioma</label>
              {catalogs ? (
                <select
                  className="select"
                  value={lang.language ?? ""}
                  onChange={(e) =>
                    patch(i, {
                      language: e.target.value || null,
                      language_label:
                        catalogs.languages.find((l) => l.id === e.target.value)
                          ?.label ?? "",
                    })
                  }
                >
                  <option value="">—</option>
                  {catalogs.languages.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.label}
                    </option>
                  ))}
                </select>
              ) : (
                <select className="select" disabled title="Cargando catálogos…">
                  <option>Cargando catálogos…</option>
                </select>
              )}
            </div>
            <div className="field">
              <label>Academia / institución</label>
              <input
                className="input"
                value={lang.academy ?? ""}
                onChange={(e) => patch(i, { academy: e.target.value })}
              />
            </div>
          </div>
          <div className="form-grid">
            {(
              [
                ["level", "Nivel general"],
                ["listening", "Listening"],
                ["reading", "Reading"],
                ["writing", "Writing"],
                ["speaking", "Speaking"],
              ] as Array<[keyof LanguageEntry, string]>
            ).map(([key, label]) => (
              <div className="field" key={key}>
                <label>{label}</label>
                <select
                  className="select"
                  value={(lang[key] as string | null) ?? ""}
                  onChange={(e) =>
                    patch(i, { [key]: e.target.value || null } as Partial<LanguageEntry>)
                  }
                >
                  <option value="">—</option>
                  {levels.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </div>
            ))}
            <div className="field">
              <label>&nbsp;</label>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => onChange(languages.filter((_, j) => j !== i))}
              >
                Quitar idioma
              </button>
            </div>
          </div>
        </div>
      ))}
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() =>
          onChange([
            ...languages,
            {
              id: `lang-${Date.now()}`,
              language: null,
              language_label: "",
              academy: "",
              level: null,
              listening: null,
              reading: null,
              writing: null,
              speaking: null,
            },
          ])
        }
      >
        + Agregar idioma
      </button>
    </div>
  );
}

function EntrySection({
  entries,
  section,
  catalogs,
  onPatch,
  onAdd,
  onRemove,
  isExperienceOrEducation = false,
}: {
  entries: ProfileEntry[];
  section: SectionKey;
  catalogs: Catalogs | null;
  onPatch: (i: number, patch: Partial<ProfileEntry>) => void;
  onAdd: () => void;
  onRemove: (i: number) => void;
  isExperienceOrEducation?: boolean;
}) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div>
      {entries.length === 0 && (
        <p className="card-sub">
          {isExperienceOrEducation
            ? "Agrega experiencias/educación en el <strong>Perfil Simple</strong> para verlas aquí y añadir perspectivas."
            : "Sin entradas en esta sección."}
        </p>
      )}
      {entries.map((entry, i) => {
        const title =
          entry.title || entry.name || entry.degree || `Entrada ${i + 1}`;
        const org = entry.company || entry.institution || "";
        const dates = [entry.start_date, entry.end_date]
          .filter(Boolean)
          .join(" → ");
        return (
          <EntryCard
            key={i}
            title={title}
            subtitle={[org, dates || entry.period || ""].filter(Boolean).join(" · ")}
            badge={`${(entry.perspectives ?? []).length} perspectiva(s)`}
            onRemove={isExperienceOrEducation ? undefined : () => onRemove(i)}
            defaultOpen={open === i}
          >
            <div onClick={() => setOpen(i)}>
              {section === "experience" && (
                <ExperienceFields
                  entry={entry}
                  catalogs={catalogs}
                  onPatch={(p) => onPatch(i, p)}
                  readOnly={isExperienceOrEducation}
                />
              )}
              {section === "education" && (
                <EducationFields
                  entry={entry}
                  catalogs={catalogs}
                  onPatch={(p) => onPatch(i, p)}
                  readOnly={isExperienceOrEducation}
                />
              )}
              {section === "projects" && (
                <ProjectFields entry={entry} onPatch={(p) => onPatch(i, p)} />
              )}
              {section === "certifications" && (
                <CertificationFields
                  entry={entry}
                  onPatch={(p) => onPatch(i, p)}
                />
              )}
              <EntrySkills
                entry={entry}
                onPatch={(p) => onPatch(i, p)}
              />
              <EntryPerspectives
                entry={entry}
                onPatch={(p) => onPatch(i, p)}
              />
            </div>
          </EntryCard>
        );
      })}
      {!isExperienceOrEducation && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={onAdd}>
          + Agregar entrada
        </button>
      )}
    </div>
  );
}

function CityAutocomplete({
  value,
  catalogs,
  onChange,
}: {
  value: CityRef | null | undefined;
  catalogs: Catalogs | null;
  onChange: (next: CityRef | null) => void;
}) {
  // Sin catalogos no se escribe texto libre: un id "custom" sin catalogar
  // lo rechaza el backend. Se muestra deshabilitado hasta que carguen.
  if (!catalogs) {
    return (
      <input
        className="input"
        value={value?.label ?? ""}
        disabled
        placeholder="Cargando catálogos…"
        title="Espera a que carguen los catálogos para elegir sin errores"
      />
    );
  }
  const options = (catalogs.cities ?? []).map((c) => ({
    id: c.id,
    label: c.label,
    hint: c.country,
  }));
  return (
    <Autocomplete
      value={value?.id ?? ""}
      onChange={(id) => {
        const found = catalogs.cities.find((c) => c.id === id);
        onChange(
          found
            ? { id: found.id, label: found.label, country: found.country }
            : null,
        );
      }}
      options={options}
      // Si el valor guardado no esta en el catalogo, se agrega como opcion
      // unica para no perderlo en silencio.
      placeholder="Escribe para buscar ciudad…"
    />
  );
}

function ExperienceFields({
  entry,
  catalogs,
  onPatch,
  readOnly = false,
}: {
  entry: ProfileEntry;
  catalogs: Catalogs | null;
  onPatch: (p: Partial<ProfileEntry>) => void;
  readOnly?: boolean;
}) {
  const titleItem = catalogs
    ? resolveOptionId(entry.title, catalogs.professional_titles)
    : null;
  return (
    <div className="form-grid">
      <div className="field">
        <label>Empresa {readOnly && "(desde Perfil Simple)"}</label>
        <input
          className="input"
          value={entry.company ?? ""}
          onChange={(e) => !readOnly && onPatch({ company: e.target.value })}
          disabled={readOnly}
        />
      </div>
      <div className="field">
        <label>Cargo {readOnly && "(desde Perfil Simple)"}</label>
        {catalogs ? (
          <Autocomplete
            value={titleItem ?? ""}
            onChange={(id) =>
              !readOnly &&
              onPatch({
                title:
                  catalogs.professional_titles.find((t) => t.id === id)
                    ?.label ?? entry.title,
              })
            }
            options={catalogs.professional_titles.map((t) => ({
              id: t.id,
              label: t.label,
            }))}
            allowCustom
            customLabel="Otro (texto libre)"
            placeholder="Escribe para buscar cargo…"
            disabled={readOnly}
          />
        ) : (
          <input
            className="input"
            value={entry.title ?? ""}
            disabled
            placeholder="Cargando catálogos…"
          />
        )}
      </div>
      <div className="field">
        <label>Fecha de inicio {readOnly && "(desde Perfil Simple)"}</label>
        <DateInput
          month
          value={entry.start_date ?? null}
          onChange={(v) => !readOnly && onPatch({ start_date: v })}
          disabled={readOnly}
        />
      </div>
      <div className="field">
        <label>Fecha de finalización {readOnly && "(desde Perfil Simple)"}</label>
        <DateInput
          month
          value={entry.is_current ? null : (entry.end_date ?? null)}
          onChange={(v) => !readOnly && onPatch({ end_date: v })}
          disabled={readOnly}
        />
      </div>
      <div className="field">
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={!!entry.is_current}
            onChange={(e) =>
              !readOnly &&
              onPatch({
                is_current: e.target.checked,
                end_date: e.target.checked ? null : entry.end_date,
              })
            }
            disabled={readOnly}
          />
          Actualmente trabajo aquí
        </label>
      </div>
      {readOnly ? (
        <>
          <div className="field">
            <label>Modalidad (desde Perfil Simple)</label>
            <input className="input" value={entry.modality ? (catalogs?.modalities?.find(m => m.id === entry.modality)?.label || entry.modality) : "—"} disabled />
          </div>
          <div className="field">
            <label>Ciudad (desde Perfil Simple)</label>
            <input className="input" value={entry.city?.label || "—"} disabled />
          </div>
          <div className="field">
            <label>Tipo de contrato (desde Perfil Simple)</label>
            <input className="input" value={entry.contract_type || "—"} disabled />
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <label>Descripción general (desde Perfil Simple)</label>
            <textarea className="textarea" value={entry.description ?? ""} disabled rows={3} />
          </div>
        </>
      ) : (
        <>
          <div className="field">
            <label>Modalidad</label>
            <select
              className="select"
              value={entry.modality ?? ""}
              onChange={(e) => onPatch({ modality: e.target.value || null })}
            >
              <option value="">—</option>
              {(catalogs?.modalities ?? MODALITY_FALLBACK).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Ciudad</label>
            <CityAutocomplete value={entry.city} catalogs={catalogs} onChange={(city) => onPatch({ city })} />
          </div>
          <div className="field">
            <label>Tipo de contrato</label>
            <select
              className="select"
              value={entry.contract_type ?? ""}
              onChange={(e) => onPatch({ contract_type: e.target.value || null })}
            >
              <option value="">—</option>
              {(catalogs?.contract_types ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <label>Descripción general</label>
            <textarea
              className="textarea"
              value={entry.description ?? ""}
              onChange={(e) => onPatch({ description: e.target.value })}
            />
          </div>
        </>
      )}
    </div>
  );
}

function EducationFields({
  entry,
  catalogs,
  onPatch,
  readOnly = false,
}: {
  entry: ProfileEntry;
  catalogs: Catalogs | null;
  onPatch: (p: Partial<ProfileEntry>) => void;
  readOnly?: boolean;
}) {
  return (
    <div className="form-grid">
      {readOnly ? (
        <>
          <div className="field">
            <label>Institución (desde Perfil Simple)</label>
            <input className="input" value={entry.institution ?? entry.company ?? ""} disabled />
          </div>
          <div className="field">
            <label>Título / programa (desde Perfil Simple)</label>
            <input className="input" value={entry.degree ?? entry.title ?? ""} disabled />
          </div>
          <div className="field">
            <label>Nivel educativo (desde Perfil Simple)</label>
            <input className="input" value={entry.level ? (catalogs?.education_levels?.find(l => l.id === entry.level)?.label || entry.level) : "—"} disabled />
          </div>
          <div className="field">
            <label>Estado (desde Perfil Simple)</label>
            <input className="input" value={entry.status ? (catalogs?.entry_status?.find(s => s.id === entry.status)?.label || entry.status) : "—"} disabled />
          </div>
          <div className="field">
            <label>Fecha de inicio (desde Perfil Simple)</label>
            <input className="input" value={entry.start_date ? entry.start_date.slice(0, 7) : "—"} disabled />
          </div>
          <div className="field">
            <label>Fecha de finalización (desde Perfil Simple)</label>
            <input className="input" value={entry.end_date ? entry.end_date.slice(0, 7) : "—"} disabled />
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <label>Descripción (desde Perfil Simple)</label>
            <textarea className="textarea" value={entry.description ?? ""} disabled rows={3} />
          </div>
        </>
      ) : (
        <>
          <div className="field">
            <label>Institución</label>
            <input
              className="input"
              value={entry.institution ?? entry.company ?? ""}
              onChange={(e) => onPatch({ institution: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Título / programa</label>
            <input
              className="input"
              value={entry.degree ?? entry.title ?? ""}
              onChange={(e) => onPatch({ degree: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Nivel educativo</label>
            <select
              className="select"
              value={entry.level ?? ""}
              onChange={(e) => onPatch({ level: e.target.value || null })}
            >
              <option value="">—</option>
              {((catalogs?.education_levels ?? ENTRY_STATUS_FALLBACK) as CatalogItem[]).map(
                (l) => (
                  <option key={l.id} value={l.id}>
                    {l.label}
                  </option>
                ),
              )}
            </select>
          </div>
          <div className="field">
            <label>Estado</label>
            <select
              className="select"
              value={entry.status ?? ""}
              onChange={(e) => onPatch({ status: e.target.value || null })}
            >
              <option value="">—</option>
              {(catalogs?.entry_status ?? ENTRY_STATUS_FALLBACK).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Fecha de inicio</label>
            <DateInput
              month
              value={entry.start_date ?? null}
              onChange={(v) => onPatch({ start_date: v })}
            />
          </div>
          <div className="field">
            <label>Fecha de finalización</label>
            <DateInput
              month
              value={entry.end_date ?? null}
              onChange={(v) => onPatch({ end_date: v })}
            />
          </div>
          <div className="field" style={{ gridColumn: "1 / -1" }}>
            <label>Descripción</label>
            <textarea
              className="textarea"
              value={entry.description ?? ""}
              onChange={(e) => onPatch({ description: e.target.value })}
            />
          </div>
        </>
      )}
    </div>
  );
}

function ProjectFields({
  entry,
  onPatch,
}: {
  entry: ProfileEntry;
  onPatch: (p: Partial<ProfileEntry>) => void;
}) {
  return (
    <div className="form-grid">
      <div className="field">
        <label>Nombre</label>
        <input
          className="input"
          value={entry.name ?? entry.title ?? ""}
          onChange={(e) => onPatch({ name: e.target.value })}
        />
      </div>
      <div className="field">
        <label>URL</label>
        <input
          className="input"
          value={entry.url ?? ""}
          onChange={(e) => onPatch({ url: e.target.value })}
          placeholder="https://…"
        />
      </div>
      <div className="field">
        <label>Repositorio</label>
        <input
          className="input"
          value={entry.repo ?? ""}
          onChange={(e) => onPatch({ repo: e.target.value })}
          placeholder="https://github.com/…"
        />
      </div>
      <div className="field">
        <label>Tecnologías</label>
        <TagInput
          value={entry.technologies ?? []}
          onChange={(next) => onPatch({ technologies: next })}
          suggestions={SKILLS}
          placeholder="Escribe para buscar y Enter"
        />
      </div>
      <div className="field">
        <label>Fecha de inicio</label>
        <DateInput
          month
          value={entry.start_date ?? null}
          onChange={(v) => onPatch({ start_date: v })}
        />
      </div>
      <div className="field">
        <label>Fecha de finalización</label>
        <DateInput
          month
          value={entry.end_date ?? null}
          onChange={(v) => onPatch({ end_date: v })}
        />
      </div>
      <div className="field" style={{ gridColumn: "1 / -1" }}>
        <label>Descripción</label>
        <textarea
          className="textarea"
          value={entry.description ?? ""}
          onChange={(e) => onPatch({ description: e.target.value })}
        />
      </div>
    </div>
  );
}

function CertificationFields({
  entry,
  onPatch,
}: {
  entry: ProfileEntry;
  onPatch: (p: Partial<ProfileEntry>) => void;
}) {
  return (
    <div className="form-grid">
      <div className="field">
        <label>Nombre</label>
        <input
          className="input"
          value={entry.name ?? entry.title ?? ""}
          onChange={(e) => onPatch({ name: e.target.value })}
        />
      </div>
      <div className="field">
        <label>Institución</label>
        <input
          className="input"
          value={entry.institution ?? ""}
          onChange={(e) => onPatch({ institution: e.target.value })}
        />
      </div>
      <div className="field">
        <label>Fecha de obtención</label>
        <DateInput
          value={entry.issued_date ?? null}
          onChange={(v) => onPatch({ issued_date: v })}
        />
      </div>
      <div className="field">
        <label>Fecha de vencimiento (opcional)</label>
        <DateInput
          value={entry.expiry_date ?? null}
          onChange={(e) => onPatch({ expiry_date: e })}
        />
      </div>
      <div className="field">
        <label>ID / credencial (opcional)</label>
        <input
          className="input"
          value={entry.credential_id ?? ""}
          onChange={(e) => onPatch({ credential_id: e.target.value })}
        />
      </div>
      <div className="field">
        <label>URL de credencial (opcional)</label>
        <input
          className="input"
          value={entry.credential_url ?? ""}
          onChange={(e) => onPatch({ credential_url: e.target.value })}
          placeholder="https://…"
        />
      </div>
      <div className="field" style={{ gridColumn: "1 / -1" }}>
        <label>Descripción</label>
        <textarea
          className="textarea"
          value={entry.description ?? ""}
          onChange={(e) => onPatch({ description: e.target.value })}
        />
      </div>
    </div>
  );
}

function EntrySkills({
  entry,
  onPatch,
}: {
  entry: ProfileEntry;
  onPatch: (p: Partial<ProfileEntry>) => void;
}) {
  return (
    <div className="form-grid" style={{ marginTop: 8 }}>
      <div className="field">
        <label>Skills técnicas</label>
        <TagInput
          value={entry.technical_skills ?? []}
          onChange={(next) => onPatch({ technical_skills: next })}
          suggestions={SKILLS}
          placeholder="Escribe para buscar skill y Enter"
        />
      </div>
      <div className="field">
        <label>Skills blandas</label>
        <TagInput
          value={entry.soft_skills ?? []}
          onChange={(next) => onPatch({ soft_skills: next })}
          suggestions={SOFT_SKILLS_FALLBACK}
          placeholder="Escribe para buscar skill y Enter"
        />
      </div>
    </div>
  );
}

function EntryPerspectives({
  entry,
  onPatch,
}: {
  entry: ProfileEntry;
  onPatch: (p: Partial<ProfileEntry>) => void;
}) {
  const perspectives = entry.perspectives ?? [];
  const patchOne = (
    k: number,
    p: Partial<import("../types/profile").Perspective>,
  ) =>
    onPatch({
      perspectives: perspectives.map((prev, j) =>
        j === k ? { ...prev, ...p } : prev,
      ),
    });
  return (
    <div style={{ marginTop: 8 }}>
      <h4 style={{ margin: "8px 0" }}>
        Perspectivas ({perspectives.length})
      </h4>
      <p className="card-sub">
        Distintas formas de presentar estos mismos hechos según la vacante.
        Solo se selecciona y reorganiza; nunca se inventa.
      </p>
      {perspectives.map((p, k) => (
        <div
          key={k}
          style={{
            background: "var(--surface-2)",
            borderRadius: 8,
            padding: 10,
            marginBottom: 8,
          }}
        >
          <div className="form-grid">
            <div className="field">
              <label>Etiqueta</label>
              <input
                className="input"
                value={p.label}
                onChange={(e) => patchOne(k, { label: e.target.value })}
                placeholder="Data Analytics"
              />
            </div>
            <div className="field">
              <label>Roles afines</label>
              <TagInput
                value={p.roles ?? []}
                onChange={(next) => patchOne(k, { roles: next })}
                suggestions={TITLE_CATEGORY_SUGGESTIONS}
                placeholder="Escribe para buscar rol y Enter"
              />
            </div>
          </div>
          <div className="field">
            <label>Descripción (hechos reales de esta óptica)</label>
            <textarea
              className="textarea"
              value={p.description}
              onChange={(e) => patchOne(k, { description: e.target.value })}
            />
          </div>
          <div className="form-grid">
            <div className="field">
              <label>Skills</label>
              <TagInput
                value={p.skills ?? []}
                onChange={(next) => patchOne(k, { skills: next })}
                suggestions={SKILLS}
                placeholder="Escribe para buscar skill y Enter"
              />
            </div>
            <div className="field">
              <label>Herramientas</label>
              <TagInput
                value={p.tools ?? []}
                onChange={(next) => patchOne(k, { tools: next })}
                suggestions={SKILLS}
                placeholder="Escribe para buscar y Enter"
              />
            </div>
            <div className="field">
              <label>Dominios</label>
              <TagInput
                value={p.domains ?? []}
                onChange={(next) => patchOne(k, { domains: next })}
                suggestions={DOMAIN_SUGGESTIONS}
                placeholder="Escribe para buscar y Enter"
              />
            </div>
            <div className="field">
              <label>&nbsp;</label>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() =>
                  onPatch({
                    perspectives: perspectives.filter((_, j) => j !== k),
                  })
                }
              >
                Quitar perspectiva
              </button>
            </div>
          </div>
        </div>
      ))}
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() =>
          onPatch({
            perspectives: [
              ...perspectives,
              {
                id: "",
                label: "",
                description: "",
                skills: [],
                tools: [],
                domains: [],
                roles: [],
              },
            ],
          })
        }
      >
        + Agregar perspectiva
      </button>
    </div>
  );
}
