import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Download,
  FileText,
  Pause,
  Play,
  PlayCircle,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import { Header } from "../components/layout/Header";
import { SuggestInput } from "../components/forms/SuggestInput";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import {
  createSearchProfile,
  deleteProfileCv,
  deleteSearchProfile,
  fetchProfileCv,
  fetchSchedulerStatus,
  fetchSearchProfiles,
  profileCvDownloadUrl,
  runSearchProfile,
  updateSearchProfile,
  uploadProfileCv,
} from "../services/searchProfiles";
import { fetchSources } from "../services/jobs";
import { fetchCatalogs } from "../services/profile";
import type { Catalogs } from "../types/profile";
import type {
  ProfileCvStatus,
  SchedulerStatus,
  SearchProfile,
} from "../types/searchProfile";
import { COLOMBIAN_CITIES } from "../utils/cities";
import { SKILLS } from "../utils/skills";
import { TITLES } from "../utils/titles";

const EMPTY_FORM = {
  name: "",
  title: "",
  location: "",
  modality: "",
  sources: [] as string[],
  active: true,
  frequency_minutes: 10,
  max_age_days: 0,
};

const FREQUENCY_OPTIONS = [
  { value: 5, label: "Cada 5 minutos" },
  { value: 10, label: "Cada 10 minutos" },
  { value: 20, label: "Cada 20 minutos" },
  { value: 30, label: "Cada 30 minutos" },
  { value: 45, label: "Cada 45 minutos" },
  { value: 60, label: "Cada hora" },
  { value: 120, label: "Cada 2 horas" },
  { value: 300, label: "Cada 5 horas" },
  { value: 600, label: "Cada 10 horas" },
  { value: 900, label: "Cada 15 horas" },
  { value: 1440, label: "Cada 24 horas" },
];

const MODALITY_FALLBACK = ["Presencial", "Híbrido", "Remoto"];

export const MAX_AGE_OPTIONS = [
  { value: 0, label: "Todas (sin límite)" },
  { value: 1, label: "Hoy" },
  { value: 3, label: "Últimos 3 días" },
  { value: 7, label: "Últimos 7 días" },
  { value: 14, label: "Últimos 14 días" },
  { value: 30, label: "Últimos 30 días" },
];

export function maxAgeLabel(days: number | null | undefined): string {
  const opt = MAX_AGE_OPTIONS.find((o) => o.value === (days ?? 0));
  return opt ? opt.label : `${days} días`;
}

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

function formatBytes(n: number | null | undefined): string {
  const bytes = n ?? 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
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
  const [confirming, setConfirming] = useState<string | null>(null);
  const [cvMap, setCvMap] = useState<Record<string, ProfileCvStatus>>({});
  const [cvBusy, setCvBusy] = useState<string | null>(null);
  // Palabras relacionadas: una por fila, con autocompletado y botón +.
  const [kwRows, setKwRows] = useState<string[]>([""]);
  const [catalogs, setCatalogs] = useState<Catalogs | null>(null);

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
      // CVs de referencia (uno por perfil): un fallo individual no
      // rompe la lista.
      const cvs = await Promise.all(
        list.map((p) =>
          fetchProfileCv(p.id).catch(
            () => ({ profile_id: p.id, has_cv: false }) as ProfileCvStatus,
          ),
        ),
      );
      setCvMap(Object.fromEntries(cvs.map((c) => [c.profile_id, c])));
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

  useEffect(() => {
    fetchCatalogs()
      .then(setCatalogs)
      .catch(() => setCatalogs(null));
  }, []);

  const titleOptions = useMemo(
    () => catalogs?.professional_titles.map((t) => t.label) ?? TITLES,
    [catalogs],
  );
  const cityOptions = useMemo(
    () => catalogs?.cities.map((c) => c.label) ?? COLOMBIAN_CITIES,
    [catalogs],
  );
  const modalityOptions = useMemo(
    () => catalogs?.modalities.map((m) => m.label) ?? MODALITY_FALLBACK,
    [catalogs],
  );

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setKwRows([""]);
    setCreating(true);
    setEditing(null);
  };

  const openEdit = (p: SearchProfile) => {
    setForm({
      name: p.name,
      title: p.title,
      location: p.location ?? "",
      modality: p.modality ?? "",
      sources: p.sources,
      active: p.active,
      frequency_minutes: p.frequency_minutes,
      max_age_days: p.max_age_days ?? 0,
    });
    setKwRows(p.keywords.length > 0 ? [...p.keywords] : [""]);
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
        keywords: [...new Set(kwRows.map((k) => k.trim()).filter(Boolean))],
        sources: form.sources,
        active: form.active,
        frequency_minutes: Number(form.frequency_minutes) || 10,
        max_age_days: Number(form.max_age_days) || 0,
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
    setBusyId(p.id);
    setConfirming(null);
    try {
      await deleteSearchProfile(p.id);
      await load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Error eliminando perfil");
    } finally {
      setBusyId(null);
    }
  };

  const uploadCv = async (p: SearchProfile, file: File | undefined) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setNotice("Solo se aceptan archivos PDF.");
      return;
    }
    setCvBusy(p.id);
    setNotice(null);
    try {
      const st = await uploadProfileCv(p.id, file);
      setCvMap((m) => ({ ...m, [p.id]: st }));
      setNotice(
        `CV de referencia guardado en "${p.name}" (${st.pages ?? 0} pág.).`,
      );
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Error subiendo el CV");
    } finally {
      setCvBusy(null);
    }
  };

  const removeCv = async (p: SearchProfile) => {
    setCvBusy(p.id);
    setNotice(null);
    try {
      await deleteProfileCv(p.id);
      setCvMap((m) => ({ ...m, [p.id]: { profile_id: p.id, has_cv: false } }));
      setNotice(`CV de referencia eliminado de "${p.name}".`);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Error eliminando el CV");
    } finally {
      setCvBusy(null);
    }
  };

  const runNow = async (p: SearchProfile) => {    setBusyId(p.id);
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
                    <SuggestInput
                      value={form.title}
                      onChange={(v) => setForm({ ...form, title: v })}
                      options={titleOptions}
                      placeholder="Analista de Datos"
                      title="Escribe y elige de la lista"
                    />
                  </label>
                  <label>
                    Ubicación
                    <SuggestInput
                      value={form.location}
                      onChange={(v) => setForm({ ...form, location: v })}
                      options={cityOptions}
                      placeholder="Bogotá"
                      title="Escribe y elige de la lista"
                    />
                  </label>
                  <label>
                    Modalidad
                    <select
                      className="select"
                      value={form.modality}
                      onChange={(e) => setForm({ ...form, modality: e.target.value })}
                    >
                      <option value="">Cualquiera</option>
                      {modalityOptions.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="field" style={{ marginTop: 6 }}>
                  <label>Palabras relacionadas (una por fila)</label>
                  {kwRows.map((kw, i) => (
                    <div className="kw-row" key={i}>
                      <SuggestInput
                        value={kw}
                        onChange={(v) =>
                          setKwRows((rows) =>
                            rows.map((r, j) => (j === i ? v : r)),
                          )
                        }
                        options={SKILLS}
                        placeholder="Ej: DAX"
                        title="Escribe y elige de la lista"
                      />
                      {kwRows.length > 1 && (
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() =>
                            setKwRows((rows) => rows.filter((_, j) => j !== i))
                          }
                          title="Quitar palabra"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  ))}
                  <div>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setKwRows((rows) => [...rows, ""])}
                    >
                      <Plus size={14} /> Añadir palabra
                    </button>
                  </div>
                </div>
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
                    Frecuencia de búsqueda
                    <select
                      className="select"
                      value={String(form.frequency_minutes)}
                      onChange={(e) =>
                        setForm({ ...form, frequency_minutes: Number(e.target.value) })
                      }
                      title="Cada cuánto ejecuta el backend este perfil"
                    >
                      {FREQUENCY_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Antigüedad máxima (por defecto)
                    <select
                      className="select"
                      value={String(form.max_age_days)}
                      onChange={(e) =>
                        setForm({ ...form, max_age_days: Number(e.target.value) })
                      }
                      title="Qué tan atrás trae vacantes: filtra por fecha de publicación antes de guardar. Sin fecha se conserva."
                    >
                      {MAX_AGE_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div style={{ marginTop: 8 }}>
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
                        <h3 className="job-title">
                          {p.name}{" "}
                          {p.is_demo && (
                            <span
                              className="badge badge-match-mid"
                              title="Perfil de prueba del modo invitado"
                            >
                              DEMO
                            </span>
                          )}
                        </h3>
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
                          <span>
                            Antigüedad máx.: {maxAgeLabel(p.max_age_days)}
                          </span>
                        </div>
                        {p.last_error && (
                          <p style={{ fontSize: 12, color: "var(--danger)" }}>
                            Error: {p.last_error}
                          </p>
                        )}
                        <div className="cv-ref">
                          <FileText size={14} />
                          {(() => {
                            const cv = cvMap[p.id];
                            const busy = cvBusy === p.id;
                            if (!cv) {
                              return (
                                <span className="cv-ref-muted">
                                  Cargando CV…
                                </span>
                              );
                            }
                            if (!cv.has_cv) {
                              return (
                                <>
                                  <span className="cv-ref-muted">
                                    Sin CV de referencia (será el ejemplo
                                    para sus ofertas)
                                  </span>
                                  <span className="spacer" />
                                  <label
                                    className="btn btn-ghost btn-sm"
                                    style={{
                                      opacity: busy ? 0.55 : 1,
                                      pointerEvents: busy ? "none" : "auto",
                                    }}
                                  >
                                    <Upload size={14} />{" "}
                                    {busy ? "Subiendo…" : "Subir PDF"}
                                    <input
                                      type="file"
                                      accept="application/pdf,.pdf"
                                      hidden
                                      disabled={busy}
                                      onChange={(e) => {
                                        void uploadCv(
                                          p,
                                          e.target.files?.[0],
                                        );
                                        e.target.value = "";
                                      }}
                                    />
                                  </label>
                                </>
                              );
                            }
                            return (
                              <>
                                <span>
                                  <strong>{cv.filename}</strong> ·{" "}
                                  {cv.pages ?? 0} pág. ·{" "}
                                  {formatBytes(cv.size_bytes)} ·{" "}
                                  {formatDateTime(cv.uploaded_at ?? null)}
                                </span>
                                {(cv.chars ?? 0) === 0 && (
                                  <span
                                    className="cv-ref-warn"
                                    title="El PDF no trae texto extraíble (escaneado?): solo sirve como archivo, no como ejemplo de generación."
                                  >
                                    sin texto
                                  </span>
                                )}
                                <span className="spacer" />
                                <a
                                  className="btn btn-ghost btn-sm"
                                  href={profileCvDownloadUrl(p.id)}
                                >
                                  <Download size={14} /> Descargar
                                </a>
                                <label
                                  className="btn btn-ghost btn-sm"
                                  style={{
                                    opacity: busy ? 0.55 : 1,
                                    pointerEvents: busy ? "none" : "auto",
                                  }}
                                  title="Reemplazar el PDF actual"
                                >
                                  <Upload size={14} />{" "}
                                  {busy ? "Subiendo…" : "Reemplazar"}
                                  <input
                                    type="file"
                                    accept="application/pdf,.pdf"
                                    hidden
                                    disabled={busy}
                                    onChange={(e) => {
                                      void uploadCv(p, e.target.files?.[0]);
                                      e.target.value = "";
                                    }}
                                  />
                                </label>
                                <button
                                  className="btn btn-ghost btn-sm"
                                  disabled={busy}
                                  onClick={() => removeCv(p)}
                                >
                                  <Trash2 size={14} /> Eliminar
                                </button>
                              </>
                            );
                          })()}
                        </div>
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
                      {confirming === p.id ? (
                        <>
                          <button
                            className="btn btn-primary btn-sm"
                            disabled={busyId === p.id}
                            onClick={() => remove(p)}
                            title="Confirma la eliminación"
                          >
                            <Trash2 size={14} /> Sí, eliminar
                          </button>
                          <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => setConfirming(null)}
                          >
                            Cancelar
                          </button>
                        </>
                      ) : (
                        <button
                          className="btn btn-ghost btn-sm"
                          disabled={busyId === p.id}
                          onClick={() => setConfirming(p.id)}
                        >
                          <Trash2 size={14} /> Eliminar
                        </button>
                      )}
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
