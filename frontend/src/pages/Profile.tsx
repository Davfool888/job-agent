import { useState } from "react";
import { Header } from "../components/layout/Header";
import {
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { useProfile } from "../hooks/useApi";
import type { Profile } from "../types/profile";

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
      </div>
    </>
  );
}
