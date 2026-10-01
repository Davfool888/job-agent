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
import { useProfile } from "../hooks/useApi";
import {
  fetchCatalogs,
  fetchFullProfile,
  saveFullProfile,
} from "../services/profile";
import type {
  Catalogs,
  CityRef,
  LanguageEntry,
  Profile,
  ProfileEntry,
  RichProfile,
} from "../types/profile";

function splitList(v: string): string[] {
  return v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function ProfilePage() {
  const { data, loading, error, reload, save, saving } = useProfile();
  const [form, setForm] = useState<Profile | null>(null);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

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

  const current = form ?? data;

  const set = (patch: Partial<Profile>) => {
    setForm({ ...current, ...patch });
    setSaved(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
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

  const setList = (key: "skills" | "target_roles" | "sectors", raw: string) =>
    set({ [key]: splitList(raw) } as Partial<Profile>);

  return (
    <>
      <Header
        title="Perfil profesional"
        subtitle="Fuente estructurada para matching, CV y análisis (PUT /profile y /profile/full)"
      />
      <div className="content">
        {data.scope === "own" && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>
              👤 Este es <strong>tu perfil personal</strong>: empieza en
              blanco y solo se llena con lo que guardes aquí. El perfil
              base de la cuenta principal no es visible para ti.
            </p>
          </div>
        )}
        <form className="card" onSubmit={submit}>
          {saveError && <div className="alert-error">{saveError}</div>}
          {saved && (
            <div className="alert-success">
              Perfil guardado en el backend.
            </div>
          )}
          <h3 className="card-title">Información personal</h3>
          <div className="form-grid">
            <div className="field">
              <label>Nombre</label>
              <input className="input" value={current.full_name} onChange={(e) => set({ full_name: e.target.value })} />
            </div>
            <div className="field">
              <label>Título profesional</label>
              <input className="input" value={current.title} onChange={(e) => set({ title: e.target.value })} placeholder="Ej: Analista de Datos" />
            </div>
            <div className="field">
              <label>Ubicación</label>
              <input className="input" value={current.location} onChange={(e) => set({ location: e.target.value })} placeholder="Ej: Bogotá, Colombia" />
            </div>
          </div>

          <h3 className="card-title" style={{ marginTop: 8 }}>
            Habilidades
          </h3>
          <p className="card-sub">Separadas por comas. Ej: Python, SQL, Power BI</p>
          <div className="field">
            <label>Habilidades</label>
            <textarea
              className="textarea"
              value={current.skills.join(", ")}
              onChange={(e) => setList("skills", e.target.value)}
            />
          </div>

          <h3 className="card-title" style={{ marginTop: 8 }}>
            Preferencias laborales
          </h3>
          <div className="form-grid">
            <div className="field">
              <label>Cargos objetivo (coma)</label>
              <input className="input" value={current.target_roles.join(", ")} onChange={(e) => setList("target_roles", e.target.value)} />
            </div>
            <div className="field">
              <label>Sectores de interés (coma)</label>
              <input className="input" value={current.sectors.join(", ")} onChange={(e) => setList("sectors", e.target.value)} />
            </div>
            <div className="field">
              <label>Modalidad</label>
              <input className="input" value={current.modality} onChange={(e) => set({ modality: e.target.value })} placeholder="Ej: Híbrido" />
            </div>
            <div className="field">
              <label>Ubicación preferida</label>
              <input className="input" value={current.preferred_location} onChange={(e) => set({ preferred_location: e.target.value })} />
            </div>
            <div className="field">
              <label>Salario mínimo</label>
              <input className="input" value={current.min_salary} onChange={(e) => set({ min_salary: e.target.value })} />
            </div>
            <div className="field">
              <label>Nivel de experiencia</label>
              <input className="input" value={current.experience_level} onChange={(e) => set({ experience_level: e.target.value })} placeholder="Ej: Junior" />
            </div>
          </div>

          <button className="btn btn-primary" disabled={saving}>
            {saving ? "Guardando…" : "Guardar perfil"}
          </button>
        </form>
        <StructuredProfileManager />
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

type SectionKey = "experience" | "education" | "projects" | "certifications";

const SECTIONS: Array<{ key: SectionKey; label: string }> = [
  { key: "experience", label: "Experiencia laboral" },
  { key: "education", label: "Educación" },
  { key: "projects", label: "Proyectos" },
  { key: "certifications", label: "Certificaciones" },
];

function StructuredProfileManager() {
  const { catalogs, error: catalogError } = useCatalogs();
  const [rich, setRich] = useState<RichProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [section, setSection] = useState<SectionKey>("experience");
  const [saving, setSaving] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await fetchFullProfile();
      setRich({
        ...data,
        technical_skills: data.technical_skills ?? [],
        soft_skills: data.soft_skills ?? [],
        years_experience: data.years_experience ?? null,
      });
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
    if (!rich) return;
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
      <h3 className="card-title">Perfil estructurado</h3>
      <p className="card-sub">
        Información de contacto, experiencia, educación, idiomas y skills con
        valores normalizados (listas, fechas, catálogos). Lo que guardes aquí
        alimenta matching, perspectivas y CV.
      </p>
      {!rich && !loading && (
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

          <h4 style={{ margin: "12px 0 8px" }}>Información personal</h4>
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
                  onChange={(e) =>
                    patchPersonal({ title_label: e.target.value })
                  }
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

          <h4 style={{ margin: "12px 0 8px" }}>Información de contacto</h4>
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
                  onChange={(e) =>
                    update({
                      ...rich,
                      personal: {
                        ...rich.personal,
                        preferred_location: e.target.value,
                      },
                    })
                  }
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
                {(catalogs?.modalities ?? []).map((m) => (
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
                placeholder="Agregar skill técnica"
              />
            </div>
            <div className="field">
              <label>Skills blandas generales</label>
              <TagInput
                value={rich.soft_skills ?? []}
                onChange={(next) => update({ ...rich, soft_skills: next })}
                placeholder="Agregar skill blanda"
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
          <div className="toolbar-row" style={{ marginBottom: 12 }}>
            {SECTIONS.map((s) => (
              <button
                key={s.key}
                type="button"
                className={`btn btn-sm ${section === s.key ? "btn-primary" : "btn-ghost"}`}
                onClick={() => setSection(s.key)}
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
            onAdd={() =>
              setEntries([
                ...entries,
                { title: "", perspectives: [] } as ProfileEntry,
              ])
            }
            onRemove={(i) => setEntries(entries.filter((_, j) => j !== i))}
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
                <input
                  className="input"
                  value={lang.language_label ?? ""}
                  onChange={(e) =>
                    patch(i, { language_label: e.target.value })
                  }
                />
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
}: {
  entries: ProfileEntry[];
  section: SectionKey;
  catalogs: Catalogs | null;
  onPatch: (i: number, patch: Partial<ProfileEntry>) => void;
  onAdd: () => void;
  onRemove: (i: number) => void;
}) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div>
      {entries.length === 0 && (
        <p className="card-sub">Sin entradas en esta sección.</p>
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
            onRemove={() => onRemove(i)}
            defaultOpen={open === i}
          >
            <div onClick={() => setOpen(i)}>
              {section === "experience" && (
                <ExperienceFields
                  entry={entry}
                  catalogs={catalogs}
                  onPatch={(p) => onPatch(i, p)}
                />
              )}
              {section === "education" && (
                <EducationFields
                  entry={entry}
                  catalogs={catalogs}
                  onPatch={(p) => onPatch(i, p)}
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
      <button type="button" className="btn btn-ghost btn-sm" onClick={onAdd}>
        + Agregar entrada
      </button>
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
  if (!catalogs) {
    return (
      <input
        className="input"
        value={value?.label ?? ""}
        onChange={(e) =>
          onChange(
            e.target.value
              ? { id: "custom", label: e.target.value, country: null }
              : null,
          )
        }
        placeholder="Ciudad"
      />
    );
  }
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
      options={catalogs.cities.map((c) => ({
        id: c.id,
        label: c.label,
        hint: c.country,
      }))}
      placeholder="Escribe para buscar ciudad…"
    />
  );
}

function ExperienceFields({
  entry,
  catalogs,
  onPatch,
}: {
  entry: ProfileEntry;
  catalogs: Catalogs | null;
  onPatch: (p: Partial<ProfileEntry>) => void;
}) {
  return (
    <div className="form-grid">
      <div className="field">
        <label>Empresa</label>
        <input
          className="input"
          value={entry.company ?? ""}
          onChange={(e) => onPatch({ company: e.target.value })}
        />
      </div>
      <div className="field">
        <label>Cargo</label>
        <input
          className="input"
          value={entry.title ?? ""}
          onChange={(e) => onPatch({ title: e.target.value })}
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
          value={entry.is_current ? null : (entry.end_date ?? null)}
          onChange={(v) => onPatch({ end_date: v })}
        />
      </div>
      <div className="field">
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input
            type="checkbox"
            checked={!!entry.is_current}
            onChange={(e) =>
              onPatch({
                is_current: e.target.checked,
                end_date: e.target.checked ? null : entry.end_date,
              })
            }
          />
          Actualmente trabajo aquí
        </label>
      </div>
      <div className="field">
        <label>Modalidad</label>
        <select
          className="select"
          value={entry.modality ?? ""}
          onChange={(e) => onPatch({ modality: e.target.value || null })}
        >
          <option value="">—</option>
          <option value="ONSITE">Presencial</option>
          <option value="HYBRID">Híbrido</option>
          <option value="REMOTE">Remoto</option>
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
    </div>
  );
}

function EducationFields({
  entry,
  catalogs,
  onPatch,
}: {
  entry: ProfileEntry;
  catalogs: Catalogs | null;
  onPatch: (p: Partial<ProfileEntry>) => void;
}) {
  return (
    <div className="form-grid">
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
          {(catalogs?.education_levels ?? []).map((l) => (
            <option key={l.id} value={l.id}>
              {l.label}
            </option>
          ))}
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
          <option value="finished">Finalizado</option>
          <option value="in_progress">En curso</option>
          <option value="abandoned">Abandonado</option>
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
        <label>Tecnologías (coma)</label>
        <input
          className="input"
          value={(entry.technologies ?? []).join(", ")}
          onChange={(e) =>
            onPatch({
              technologies: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
            })
          }
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
          placeholder="Agregar skill técnica"
        />
      </div>
      <div className="field">
        <label>Skills blandas</label>
        <TagInput
          value={entry.soft_skills ?? []}
          onChange={(next) => onPatch({ soft_skills: next })}
          placeholder="Agregar skill blanda"
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
  const patchOne = (k: number, p: Partial<import("../types/profile").Perspective>) =>
    onPatch({
      perspectives: perspectives.map((prev, j) =>
        j === k ? { ...prev, ...p } : prev,
      ),
    });
  const setList = (
    k: number,
    field: "skills" | "tools" | "domains" | "roles",
    raw: string,
  ) =>
    patchOne(k, {
      [field]: raw.split(",").map((s) => s.trim()).filter(Boolean),
    } as Partial<import("../types/profile").Perspective>);
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
              <label>Roles afines (coma)</label>
              <input
                className="input"
                value={(p.roles ?? []).join(", ")}
                onChange={(e) => setList(k, "roles", e.target.value)}
                placeholder="DATA_ANALYST, BI_ANALYST"
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
              <label>Skills (coma)</label>
              <input
                className="input"
                value={(p.skills ?? []).join(", ")}
                onChange={(e) => setList(k, "skills", e.target.value)}
              />
            </div>
            <div className="field">
              <label>Herramientas (coma)</label>
              <input
                className="input"
                value={(p.tools ?? []).join(", ")}
                onChange={(e) => setList(k, "tools", e.target.value)}
              />
            </div>
            <div className="field">
              <label>Dominios (coma)</label>
              <input
                className="input"
                value={(p.domains ?? []).join(", ")}
                onChange={(e) => setList(k, "domains", e.target.value)}
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
