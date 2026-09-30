import { useState } from "react";
import { Header } from "../components/layout/Header";
import {
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { useProfile } from "../hooks/useApi";
import { fetchFullProfile, saveFullProfile } from "../services/profile";
import type { Perspective, Profile, ProfileEntry, RichProfile } from "../types/profile";

function splitList(v: string): string[] {
  return v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function ProfilePage() {
  const { data, loading, error, reload, save, saving } = useProfile();
  // `form` nulo = aun sin edicion: se muestra lo del backend.
  // Sin useEffect: se evita setState sincronico en efectos.
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
    }
  };

  const setList = (key: "skills" | "target_roles" | "sectors", raw: string) =>
    set({ [key]: splitList(raw) } as Partial<Profile>);

  return (
    <>
      <Header
        title="Perfil profesional"
        subtitle="Base que usará el agente para calcular la coincidencia (persistido en el backend: PUT /profile)"
      />
      <div className="content">
          <form className="card" onSubmit={submit}>
            {saveError && <div className="alert-error">{saveError}</div>}
            {saved && (
              <div
                className="alert-error"
                style={{
                  background: "var(--success-soft)",
                  borderColor: "#bfe3cf",
                  color: "var(--success)",
                }}
              >
                Perfil guardado en el backend.
              </div>
            )}
            <h3 className="card-title">Información</h3>
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
              <div className="field">
                <label>LinkedIn</label>
                <input className="input" value={current.linkedin} onChange={(e) => set({ linkedin: e.target.value })} placeholder="https://…" />
              </div>
              <div className="field">
                <label>GitHub</label>
                <input className="input" value={current.github} onChange={(e) => set({ github: e.target.value })} placeholder="https://…" />
              </div>
              <div className="field">
                <label>Portfolio</label>
                <input className="input" value={current.portfolio} onChange={(e) => set({ portfolio: e.target.value })} placeholder="https://…" />
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
          <PerspectivesManager />
      </div>
    </>
  );
}

const SECTIONS = [
  { key: "experience", label: "Experiencias" },
  { key: "education", label: "Educación" },
  { key: "projects", label: "Proyectos" },
  { key: "certifications", label: "Certificaciones" },
] as const;

type SectionKey = (typeof SECTIONS)[number]["key"];

const EMPTY_PERSPECTIVE: Perspective = {
  id: "",
  label: "",
  description: "",
  skills: [],
  tools: [],
  domains: [],
  roles: [],
};

function joinList(v: string[]): string {
  return v.join(", ");
}

function PerspectivesManager() {
  const [rich, setRich] = useState<RichProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [section, setSection] = useState<SectionKey>("experience");
  const [openEntry, setOpenEntry] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await fetchFullProfile();
      setRich(data);
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

  const entries = (rich?.[section] ?? []) as ProfileEntry[];

  const setEntries = (next: ProfileEntry[]) => {
    if (!rich) return;
    update({ ...rich, [section]: next });
  };

  const addEntry = () => {
    setEntries([...entries, { title: "", company: "", period: "", perspectives: [] }]);
    setOpenEntry(entries.length);
  };

  const patchEntry = (i: number, patch: Partial<ProfileEntry>) => {
    setEntries(entries.map((e, j) => (j === i ? { ...e, ...patch } : e)));
  };

  const removeEntry = (i: number) => {
    setEntries(entries.filter((_, j) => j !== i));
    setOpenEntry(null);
  };

  const addPerspective = (i: number) => {
    const e = entries[i];
    patchEntry(i, {
      perspectives: [...(e.perspectives ?? []), { ...EMPTY_PERSPECTIVE }],
    });
  };

  const patchPerspective = (
    i: number,
    k: number,
    patch: Partial<Perspective>,
  ) => {
    const e = entries[i];
    patchEntry(i, {
      perspectives: (e.perspectives ?? []).map((p, j) =>
        j === k ? { ...p, ...patch } : p,
      ),
    });
  };

  const removePerspective = (i: number, k: number) => {
    const e = entries[i];
    patchEntry(i, {
      perspectives: (e.perspectives ?? []).filter((_, j) => j !== k),
    });
  };

  const setListField = (
    i: number,
    k: number,
    field: "skills" | "tools" | "domains" | "roles",
    raw: string,
  ) => {
    patchPerspective(i, k, {
      [field]: raw.split(",").map((s) => s.trim()).filter(Boolean),
    } as Partial<Perspective>);
  };

  const submit = async () => {
    if (!rich) return;
    setSaving(true);
    setSaveError(null);
    try {
      const out = await saveFullProfile(rich);
      setRich({ ...out.profile, _warnings: out.warnings });
      setWarnings(out.warnings);
      setSaved(true);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Error inesperado");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 className="card-title">Experiencias y perspectivas</h3>
      <p className="card-sub">
        Una experiencia puede tener varias perspectivas (p. ej. Comercial y
        Data Analytics): cada una describe qué parte real es relevante para
        cierto tipo de vacante. La información base (cargo, empresa, fechas)
        queda bloqueada para la adaptación automática: el agente solo
        selecciona y reorganiza, nunca inventa.
      </p>
      {!rich && !loading && (
        <button className="btn btn-ghost btn-sm" onClick={load}>
          Cargar perfil modular
        </button>
      )}
      {loading && <LoadingState label="Cargando perfil modular…" />}
      {loadError && <ErrorState message={loadError} onRetry={load} />}
      {rich && (
        <>
          <div className="toolbar-row" style={{ marginBottom: 12 }}>
            {SECTIONS.map((s) => (
              <button
                key={s.key}
                className={`btn btn-sm ${section === s.key ? "btn-primary" : "btn-ghost"}`}
                onClick={() => {
                  setSection(s.key);
                  setOpenEntry(null);
                }}
              >
                {s.label} ({((rich[s.key] ?? []) as ProfileEntry[]).length})
              </button>
            ))}
          </div>
          {warnings.length > 0 && (
            <div className="alert-error">
              <p style={{ margin: "0 0 6px" }}>
                <strong>Advertencias:</strong> skills no declarados en la base:
              </p>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}
          {entries.length === 0 && (
            <p className="card-sub">Sin entradas en esta sección.</p>
          )}
          {entries.map((entry, i) => (
            <div
              key={i}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: 12,
                marginBottom: 10,
              }}
            >
              <div
                style={{ display: "flex", gap: 8, alignItems: "center" }}
                onClick={() => setOpenEntry(openEntry === i ? null : i)}
              >
                <strong style={{ flex: 1, cursor: "pointer" }}>
                  {entry.title || entry.name || entry.degree || `Entrada ${i + 1}`}
                  {(entry.company || entry.institution) &&
                    ` — ${entry.company || entry.institution}`}
                </strong>
                <span className="card-sub">
                  {(entry.perspectives ?? []).length} perspectiva(s)
                </span>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeEntry(i);
                  }}
                >
                  Eliminar
                </button>
              </div>
              {openEntry === i && (
                <div style={{ marginTop: 10 }}>
                  <div className="form-grid">
                    <div className="field">
                      <label>Cargo / nombre</label>
                      <input
                        className="input"
                        value={entry.title ?? entry.name ?? entry.degree ?? ""}
                        onChange={(e) =>
                          patchEntry(i, { title: e.target.value })
                        }
                      />
                    </div>
                    <div className="field">
                      <label>Empresa / institución</label>
                      <input
                        className="input"
                        value={entry.company ?? entry.institution ?? ""}
                        onChange={(e) =>
                          patchEntry(i, { company: e.target.value })
                        }
                      />
                    </div>
                    <div className="field">
                      <label>Periodo</label>
                      <input
                        className="input"
                        value={entry.period ?? ""}
                        onChange={(e) =>
                          patchEntry(i, { period: e.target.value })
                        }
                        placeholder="2021 - 2024"
                      />
                    </div>
                    <div className="field">
                      <label>Dato factual (opcional)</label>
                      <input
                        className="input"
                        value={entry.facts ?? ""}
                        onChange={(e) =>
                          patchEntry(i, { facts: e.target.value })
                        }
                      />
                    </div>
                  </div>
                  <h4 style={{ margin: "8px 0" }}>Perspectivas</h4>
                  {(entry.perspectives ?? []).map((p, k) => (
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
                            onChange={(e) =>
                              patchPerspective(i, k, { label: e.target.value })
                            }
                            placeholder="Data Analytics"
                          />
                        </div>
                        <div className="field">
                          <label>Roles afines (coma)</label>
                          <input
                            className="input"
                            value={joinList(p.roles)}
                            onChange={(e) =>
                              setListField(i, k, "roles", e.target.value)
                            }
                            placeholder="DATA_ANALYST, BI_ANALYST"
                          />
                        </div>
                      </div>
                      <div className="field">
                        <label>Descripción (hechos reales de esta óptica)</label>
                        <textarea
                          className="textarea"
                          value={p.description}
                          onChange={(e) =>
                            patchPerspective(i, k, {
                              description: e.target.value,
                            })
                          }
                        />
                      </div>
                      <div className="form-grid">
                        <div className="field">
                          <label>Skills (coma)</label>
                          <input
                            className="input"
                            value={joinList(p.skills)}
                            onChange={(e) =>
                              setListField(i, k, "skills", e.target.value)
                            }
                          />
                        </div>
                        <div className="field">
                          <label>Herramientas (coma)</label>
                          <input
                            className="input"
                            value={joinList(p.tools)}
                            onChange={(e) =>
                              setListField(i, k, "tools", e.target.value)
                            }
                          />
                        </div>
                        <div className="field">
                          <label>Dominios (coma)</label>
                          <input
                            className="input"
                            value={joinList(p.domains)}
                            onChange={(e) =>
                              setListField(i, k, "domains", e.target.value)
                            }
                            placeholder="banking, finance"
                          />
                        </div>
                        <div className="field">
                          <label>&nbsp;</label>
                          <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => removePerspective(i, k)}
                          >
                            Quitar perspectiva
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => addPerspective(i)}
                  >
                    + Agregar perspectiva
                  </button>
                </div>
              )}
            </div>
          ))}
          <div
            style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}
          >
            <button className="btn btn-ghost btn-sm" onClick={addEntry}>
              + Agregar entrada
            </button>
            <button
              className="btn btn-primary btn-sm"
              disabled={saving}
              onClick={submit}
            >
              {saving ? "Guardando…" : "Guardar perfil modular"}
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
