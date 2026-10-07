import { useEffect, useRef, useState } from "react";
import { ErrorState, LoadingState } from "../../components/jobs/States";
import {
  Autocomplete,
  DateInput,
  EntryCard,
  TagInput,
} from "../../components/profile/fields";
import { fetchCatalogs, fetchFullProfile, fetchProfile, saveFullProfile } from "../../services/profile";
import { SKILLS } from "../../utils/skills";
import {
  DOMAIN_SUGGESTIONS,
  ENTRY_STATUS_FALLBACK,
  MODALITY_FALLBACK,
  SOFT_SKILLS_FALLBACK,
  TITLE_CATEGORY_SUGGESTIONS,
  resolveOptionId,
  splitSpanishName,
} from "../../utils/profileOptions";
import type {
  CatalogItem,
  Catalogs,
  CityRef,
  LanguageEntry,
  ProfileEntry,
  RichProfile,
} from "../../types/profile";
import { useAuth } from "../../context/AuthContext";
import { ADMIN_EMAIL } from "../../lib/firebase";

function useIsAdminSession(): boolean {
  const { firebaseUser, isGuest } = useAuth();
  if (!firebaseUser || isGuest) return false;
  return (firebaseUser.email ?? "").trim().toLowerCase() === ADMIN_EMAIL;
}

interface StructuredProfileManagerProps {
  locked: boolean;
  simpleExperiences: ProfileEntry[];
  simpleEducation: ProfileEntry[];
  simpleLanguages: LanguageEntry[];
  /** Se incrementa cuando el tab simple guarda: recarga si no hay ediciones pendientes. */
  externalRevision: number;
  /** Tras guardar aquí: el padre refresca listas simples y el plano. */
  onSaved?: (sections: {
    experience: ProfileEntry[];
    education: ProfileEntry[];
    languages: LanguageEntry[];
  }) => void;
}

const EXP_BASE_FIELDS = [
  "company",
  "title",
  "start_date",
  "end_date",
  "description",
] as const;
const EDU_BASE_FIELDS = [
  "institution",
  "degree",
  "start_date",
  "end_date",
  "description",
] as const;

function mergeBaseFields(
  richList: ProfileEntry[],
  simpleList: ProfileEntry[],
  fields: readonly string[],
): ProfileEntry[] {
  const out: ProfileEntry[] = richList.map((richExp: any, idx: number) => {
    const simpleExp = (simpleList as any[])[idx];
    if (!simpleExp) return richExp;
    const merged = { ...richExp };
    for (const f of fields) {
      const rv = (richExp as any)[f];
      const sv = (simpleExp as any)[f];
      if (f === "is_current") {
        merged[f] = rv ?? sv;
      } else if (
        rv !== undefined &&
        rv !== null &&
        String(rv).trim() !== ""
      ) {
        merged[f] = rv;
      } else if (sv !== undefined) {
        merged[f] = sv;
      }
    }
    return merged;
  });
  // Entradas que solo existen en el simple (sin guardar aun).
  for (let k = richList.length; k < simpleList.length; k++) {
    out.push({ ...(simpleList[k] as object), perspectives: [] } as ProfileEntry);
  }
  return out;
}

export function StructuredProfileManager({
  locked,
  simpleExperiences,
  simpleEducation,
  simpleLanguages,
  externalRevision,
  onSaved,
}: StructuredProfileManagerProps) {
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

  const { firebaseUser } = useAuth();
  const isAdmin = useIsAdminSession();
  const [rich, setRich] = useState<RichProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lockedRich, setLockedRich] = useState(false);
  const [section, setSection] = useState<"experience" | "education" | "projects" | "certifications">("experience");
  const [saving, setSaving] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // Ediciones pendientes: si el tab simple guarda mientras hay cambios
  // sin guardar aquí, se conservan (no se pisan con recarga).
  const dirtyRef = useRef(false);
  const loadedRevision = useRef<number | null>(null);
  const autoLoaded = useRef(false);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    setLockedRich(false);
    try {
      const data = await fetchFullProfile();      if (
        firebaseUser &&
        !isAdmin &&
        data.scope !== "own" &&
        data.scope !== "demo"
      ) {
        setLockedRich(true);
        setRich(null);
        return;
      }

      let mergedData = {
        ...data,
        technical_skills: data.technical_skills ?? [],
        soft_skills: data.soft_skills ?? [],
        years_experience: data.years_experience ?? null,
      };

      // Consistencia con el tab simple: los campos repetidos vacíos
      // se pre-rellenan desde el plano (solo display; al guardar, el
      // backend los iguala en ambos lados).
      try {
        const flat = (await fetchProfile()) as unknown as Record<string, unknown>;
        const pp = { ...(mergedData.personal ?? {}) } as Record<string, unknown>;
        const pick = (richV: unknown, flatV: unknown) =>
          String(richV ?? "").trim() ? richV : (flatV ?? richV);
        pp.full_name = pick(pp.full_name, flat.full_name);
        pp.title = pick(pp.title, flat.title);
        pp.location = pick(pp.location, flat.location);
        for (const k of ["email", "phone", "linkedin", "github", "portfolio"] as const) {
          pp[k] = pick(pp[k], flat[k]);
        }
        if (!String(pp.first_name ?? "").trim() && !String(pp.last_name ?? "").trim()) {
          const [first, last] = splitSpanishName(String(pp.full_name ?? ""));
          pp.first_name = first;
          pp.last_name = last;
        }
        mergedData.personal = pp as typeof mergedData.personal;
      } catch {
        /* sin plano: se muestra el estructurado tal cual */
      }

      if (simpleExperiences.length > 0) {
        const mergedExperiences = mergeBaseFields(
          mergedData.experience || [],
          simpleExperiences as ProfileEntry[],
          EXP_BASE_FIELDS,
        );
        // Conserva las agregadas aqui (mas alla del largo del simple).
        const richExperiences = mergedData.experience || [];
        for (let k = simpleExperiences.length; k < richExperiences.length; k++) {
          mergedExperiences.push(richExperiences[k]);
        }
        mergedData.experience = mergedExperiences;
      }

      if (simpleEducation.length > 0) {
        const mergedEducation = mergeBaseFields(
          mergedData.education || [],
          simpleEducation as ProfileEntry[],
          EDU_BASE_FIELDS,
        );
        const richEducation = mergedData.education || [];
        for (let k = simpleEducation.length; k < richEducation.length; k++) {
          mergedEducation.push(richEducation[k]);
        }
        mergedData.education = mergedEducation;
      }

      if (simpleLanguages.length > 0) {
        mergedData.languages = simpleLanguages;
      }

      setRich(mergedData);
      setWarnings(data._warnings ?? []);
      dirtyRef.current = false;
      loadedRevision.current = externalRevision;
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Error inesperado");
    } finally {
      setLoading(false);
    }
  };

  // Carga automatica al abrir el tab (sin boton adicional). El boton
  // queda como reintento si la carga falla.
  useEffect(() => {
    if (autoLoaded.current || locked) return;
    autoLoaded.current = true;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Si el tab simple guarda y aqui no hay ediciones pendientes,
  // se refresca para mostrar lo nuevo (nombre, telefono, etc.).
  useEffect(() => {
    if (
      loadedRevision.current === null ||
      loadedRevision.current === externalRevision ||
      dirtyRef.current ||
      loading
    ) {
      return;
    }
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalRevision]);

  const update = (next: RichProfile) => {
    setRich(next);
    setSaved(false);
    dirtyRef.current = true;
  };

  const patchPersonal = (patch: Record<string, string>) => {
    if (!rich) return;
    update({ ...rich, personal: { ...rich.personal, ...patch } });
  };

  type SectionKey = "experience" | "education" | "projects" | "certifications";

  const SECTIONS: Array<{ key: SectionKey; label: string }> = [
    { key: "experience", label: "Experiencia laboral" },
    { key: "education", label: "Educación" },
    { key: "projects", label: "Proyectos" },
    { key: "certifications", label: "Certificaciones" },
  ];

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
      // Base del simple como respaldo (gana lo editado aqui cuando no
      // esta vacio): lo que se ve es lo que se guarda.
      const payload: RichProfile = {
        ...rich,
        experience: mergeBaseFields(
          rich.experience ?? [],
          simpleExperiences,
          EXP_BASE_FIELDS,
        ),
        education: mergeBaseFields(
          rich.education ?? [],
          simpleEducation,
          EDU_BASE_FIELDS,
        ),
      };
      const out = await saveFullProfile(payload);
      setRich({ ...out.profile, _warnings: out.warnings } as RichProfile);
      setWarnings(out.warnings);
      setSaved(true);
      dirtyRef.current = false;
      onSaved?.({
        experience: (out.profile.experience ?? []) as ProfileEntry[],
        education: (out.profile.education ?? []) as ProfileEntry[],
        languages: (out.profile.languages ?? []) as LanguageEntry[],
      });
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
        Los datos repetidos (nombre, contacto, empresa, fechas, descripción) están <strong>sincronizados</strong>:
        lo que guardes en un tab aparece en el otro. Si editas en ambos sin guardar,
        gana el último guardado.
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
      {error && (
        <div className="alert-error">
          No se pudieron cargar los catálogos: {error}
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
            Todo se puede <strong>editar, agregar y quitar aquí</strong> y se guarda con
            “Guardar perfil estructurado”. Las perspectivas añaden ópticas por vacante
            sin duplicar la información base.
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
              const base = { perspectives: [] } as ProfileEntry;
              if (section === "experience") {
                setEntries([...entries, { ...base, title: "", company: "" }]);
              } else if (section === "education") {
                setEntries([...entries, { ...base, degree: "", institution: "" }]);
              } else if (section === "projects") {
                setEntries([...entries, { ...base, name: "" }]);
              } else {
                setEntries([...entries, { ...base, name: "" }]);
              }
            }}
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
    p: Partial<import("../../types/profile").Perspective>,
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

function EntrySection({
  entries,
  section,
  catalogs,
  onPatch,
  onAdd,
  onRemove,
}: {
  entries: ProfileEntry[];
  section: "experience" | "education" | "projects" | "certifications";
  catalogs: Catalogs | null;
  onPatch: (i: number, patch: Partial<ProfileEntry>) => void;
  onAdd: () => void;
  onRemove: (i: number) => void;
}) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div>
      {entries.length === 0 && (
        <p className="card-sub">
          Sin entradas en esta sección.
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