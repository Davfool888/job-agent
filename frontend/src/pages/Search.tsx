import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Pause, Play, PlayCircle, Plus, RefreshCw, Trash2 } from "lucide-react";
import { Header } from "../components/layout/Header";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import {
  createSearchProfile,
  deleteSearchProfile,
  fetchSchedulerStatus,
  fetchSearchProfiles,
  runSearchProfile,
  updateSearchProfile,
} from "../services/searchProfiles";
import { fetchSources } from "../services/jobs";
import type {
  SchedulerStatus,
  SearchProfile,
} from "../types/searchProfile";

const EMPTY_FORM = {
  name: "",
  title: "",
  location: "",
  modality: "",
  keywords: "",
  sources: [] as string[],
  active: true,
  frequency_minutes: 10,
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("es-CO", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function Search() {
  const [profiles, setProfiles] = useState<SearchProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [allSources, setAllSources] = useState<string[]>([]);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, status] = await Promise.all([
        fetchSearchProfiles(),
        fetchSchedulerStatus().catch(() => null),
      ]);
      setProfiles(list);
      setScheduler(status);
      try {
        setAllSources(await fetchSources());
      } catch {
        setAllSources([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error cargando perfiles");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setCreating(true);
    setEditing(null);
  };

  const openEdit = (p: SearchProfile) => {
    setForm({
      name: p.name,
      title: p.title,
      location: p.location ?? "",
      modality: p.modality ?? "",
      keywords: p.keywords.join(", "),
      sources: p.sources,
      active: p.active,
      frequency_minutes: p.frequency_minutes,
    });
    setEditing(p.id);
    setCreating(false);
  };

  const closeForm = () => {
    setCreating(false);
    setEditing(null);
  };

  const submit = async () => {
    if (!form.title.trim()) {
      setNotice("El cargo objetivo es obligatorio.");
      return;
    }
    setBusyId("form");
    setNotice(null);
    try {
      const payload = {
        name: form.name.trim() || form.title.trim(),
        title: form.title.trim(),
        location: form.location.trim() || null,
        modality: form.modality.trim() || null,
        keywords: form.keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
        sources: form.sources,
        active: form.active,
        frequency_minutes: Number(form.frequency_minutes) || 10,
      };
      if (editing) {
        await updateSearchProfile(editing, payload);
        setNotice("Perfil actualizado.");
      } else {
        await createSearchProfile(payload);
        setNotice("Perfil creado.");
      }
      closeForm();
      await load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Error guardando perfil");
    } finally {
      setBusyId(null);
    }
  };

  const toggleActive = async (p: SearchProfile) => {
    setBusyId(p.id);
    try {
      await updateSearchProfile(p.id, { active: !p.active });
      await load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Error cambiando estado");
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (p: SearchProfile) => {
    if (!window.confirm(`¿Eliminar el perfil "${p.name}"?`)) return;
    setBusyId(p.id);
    try {
      await deleteSearchProfile(p.id);
      await load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Error eliminando perfil");
    } finally {
      setBusyId(null);
    }
  };

  const runNow = async (p: SearchProfile) => {
    setBusyId(p.id);
    setNotice(null);
    try {
      const r = await runSearchProfile(p.id);
      setNotice(
        `"${p.name}": ${r.found} encontradas, ${r.new} nuevas, ${r.analyzed} analizadas.` +
          (r.errors.length ? ` ${r.errors.length} errores.` : ""),
      );
      await load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Error ejecutando perfil");
    } finally {
      setBusyId(null);
    }
  };

  const toggleSource = (s: string) => {
    setForm((f) => ({
      ...f,
      sources: f.sources.includes(s)
        ? f.sources.filter((x) => x !== s)
        : [...f.sources, s],
    }));
  };

  return (
    <>
      <Header
        title="Búsqueda automática"
        subtitle="Perfiles que el backend ejecuta cada ~10 minutos, incluso con tu PC apagado"
      />
      <div className="content">
        {scheduler && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>
              Scheduler:{" "}
              <strong>{scheduler.enabled ? "activo" : "inactivo"}</strong>
              {scheduler.last_tick.at && (
                <>
                  {" "}· Último tick: {formatDateTime(scheduler.last_tick.at)}{" "}
                  ({scheduler.last_tick.profiles} perfiles,{" "}
                  {scheduler.last_tick.new} nuevas)
                </>
              )}
              {scheduler.last_tick.error && (
                <> · Error: {scheduler.last_tick.error}</>
              )}
            </p>
            {!scheduler.enabled && (
              <p style={{ margin: "6px 0 0", fontSize: 12.5 }}>
                Activa <code>SCHEDULER_ENABLED=true</code> en el backend. En
                Render gratuito la instancia duerme: configura un cron externo
                (cron-job.org) cada 10 min hacia{" "}
                <code>POST /scheduler/tick</code>.
              </p>
            )}
          </div>
        )}
        {notice && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>{notice}</p>
          </div>
        )}

        {loading ? (
          <LoadingState label="Cargando perfiles…" />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : (
          <>
            <div style={{ marginBottom: 14 }}>
              <button className="btn btn-primary btn-sm" onClick={openCreate}>
                <Plus size={14} /> Nuevo perfil
              </button>
            </div>

            {(creating || editing) && (
              <div className="card" style={{ marginBottom: 16 }}>
                <h3 className="card-title">
                  {editing ? "Editar perfil" : "Nuevo perfil"}
                </h3>
                <div className="form-grid">
                  <label>
                    Nombre
                    <input
                      className="input"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      placeholder="Analista de Datos - Bogotá"
                    />
                  </label>
                  <label>
                    Cargo objetivo *
                    <input
                      className="input"
                      value={form.title}
                      onChange={(e) => setForm({ ...form, title: e.target.value })}
                      placeholder="Analista de Datos"
                    />
                  </label>
                  <label>
                    Ubicación
                    <input
                      className="input"
                      value={form.location}
                      onChange={(e) => setForm({ ...form, location: e.target.value })}
                      placeholder="Bogotá"
                    />
                  </label>
                  <label>
                    Modalidad
                    <input
                      className="input"
                      value={form.modality}
                      onChange={(e) => setForm({ ...form, modality: e.target.value })}
                      placeholder="Remoto / Híbrido / Presencial"
                    />
                  </label>
                </div>
                <label style={{ display: "block", marginTop: 8 }}>
                  Palabras relacionadas (separadas por coma)
                  <input
                    className="input"
                    value={form.keywords}
                    onChange={(e) => setForm({ ...form, keywords: e.target.value })}
                    placeholder="Power BI, DAX, Excel, Power Query, SQL"
                    style={{ width: "100%" }}
                  />
                </label>
                <div style={{ marginTop: 8 }}>
                  <p style={{ fontSize: 12.5, margin: "0 0 6px" }}>
                    Fuentes (vacío = todas por defecto)
                  </p>
                  {allSources.map((s) => (
                    <label
                      key={s}
                      style={{
                        display: "inline-flex",
                        gap: 6,
                        alignItems: "center",
                        fontSize: 12.5,
                        marginRight: 14,
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={form.sources.includes(s)}
                        onChange={() => toggleSource(s)}
                      />
                      {s}
                    </label>
                  ))}
                </div>
                <div className="form-grid" style={{ marginTop: 8 }}>
                  <label>
                    Frecuencia (minutos, 5–1440)
                    <input
                      className="input"
                      type="number"
                      min={5}
                      max={1440}
                      value={form.frequency_minutes}
                      onChange={(e) =>
                        setForm({ ...form, frequency_minutes: Number(e.target.value) })
                      }
                    />
                  </label>
                  <label
                    style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12.5 }}
                  >
                    <input
                      type="checkbox"
                      checked={form.active}
                      onChange={(e) => setForm({ ...form, active: e.target.checked })}
                    />
                    Activo
                  </label>
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                  <button
                    className="btn btn-primary btn-sm"
                    disabled={busyId === "form"}
                    onClick={submit}
                  >
                    {busyId === "form" ? "Guardando…" : "Guardar"}
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={closeForm}>
                    Cancelar
                  </button>
                </div>
              </div>
            )}

            {profiles.length === 0 ? (
              <EmptyState
                title="Sin perfiles de búsqueda."
                hint="Crea tu primer perfil (ej. Analista de Datos en Bogotá) y el backend lo ejecutará automáticamente."
              />
            ) : (
              <div className="job-list">
                {profiles.map((p) => (
                  <div key={p.id} className="job-card">
                    <div className="job-card-top">
                      <div className="job-card-main">
                        <h3 className="job-title">{p.name}</h3>
                        <div className="job-meta">
                          <span>{p.title}</span>
                          {p.location && <span>{p.location}</span>}
                          {p.modality && <span>{p.modality}</span>}
                          <span>
                            Estado: {p.active ? "ACTIVO" : "INACTIVO"}
                            {p.last_run_status === "running" && " (ejecutando…)"}
                          </span>
                        </div>
                        {p.keywords.length > 0 && (
                          <p className="job-desc">{p.keywords.join(" · ")}</p>
                        )}
                        <div className="job-meta">
                          <span>Última búsqueda: {formatDateTime(p.last_run_at)}</span>
                          <span>Próxima búsqueda: {formatDateTime(p.next_run_at)}</span>
                          <span>
                            Ofertas encontradas: {p.last_found} · Nuevas: {p.last_new}
                          </span>
                        </div>
                        {p.last_error && (
                          <p style={{ fontSize: 12, color: "var(--danger)" }}>
                            Error: {p.last_error}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="job-card-foot">
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={busyId === p.id}
                        onClick={() => runNow(p)}
                        title="Ejecutar ahora sin esperar la frecuencia"
                      >
                        <PlayCircle size={14} />{" "}
                        {busyId === p.id ? "Buscando…" : "Buscar ahora"}
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        disabled={busyId === p.id}
                        onClick={() => toggleActive(p)}
                      >
                        {p.active ? (
                          <>
                            <Pause size={14} /> Pausar
                          </>
                        ) : (
                          <>
                            <Play size={14} /> Activar
                          </>
                        )}
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => openEdit(p)}
                      >
                        Editar
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        disabled={busyId === p.id}
                        onClick={() => remove(p)}
                      >
                        <Trash2 size={14} /> Eliminar
                      </button>
                      <span className="spacer" />
                      <Link className="btn btn-ghost btn-sm" to="/jobs">
                        Ver ofertas <RefreshCw size={14} />
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
