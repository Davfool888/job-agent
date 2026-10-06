import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Download,
  FileText,
  ListPlus,
  Play,
  Send,
  Square,
  Trash2,
} from "lucide-react";
import { Header } from "../components/layout/Header";
import { MatchBadge } from "../components/jobs/MatchBadge";
import { useAdaptToken } from "../hooks/useAdaptToken";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { useJobs, useProfileOptions } from "../hooks/useApi";
import {
  adaptCvAsync,
  adaptDownloadUrl,
  type AdaptAsyncError,
} from "../services/adapt";
import type { Job } from "../types/job";
import { DEFAULT_FILTERS } from "../types/filters";
import type { JobFilterState } from "../types/filters";
import { JobFilters } from "../components/jobs/JobFilters";
import { applyJobFilters, profileOptions, uniqueSorted } from "../utils/jobs";

// Tope por lote para no saturar la API (PDF con Chromium es costoso).
const MAX_BATCH = 5;
const BATCH_STORE_KEY = "jobagent_adapt_batch";

interface BatchItem {
  jobId: string;
  title: string;
  company: string | null;
  status: "working" | "done" | "error";
  detail?: string;
}

function loadBatchIds(): string[] {
  try {
    const raw = window.localStorage.getItem(BATCH_STORE_KEY);
    const parsed = JSON.parse(raw ?? "[]") as unknown;
    if (Array.isArray(parsed)) {
      return parsed.filter((x): x is string => typeof x === "string");
    }
  } catch {
    /* sin batch previo */
  }
  return [];
}

export function CV() {
  const { data, loading, error, reload, mutate } = useJobs("kept");
  const dlToken = useAdaptToken();
  const allProfiles = useProfileOptions();
  const kept = useMemo(() => data ?? [], [data]);
  const [filters, setFilters] = useState<JobFilterState>(DEFAULT_FILTERS);
  const visible = useMemo(() => applyJobFilters(kept, filters), [kept, filters]);
  const companies = useMemo(() => uniqueSorted(kept, (j) => j.company), [kept]);
  const locations = useMemo(() => uniqueSorted(kept, (j) => j.location), [kept]);
  const sources = useMemo(() => uniqueSorted(kept, (j) => j.source), [kept]);
  const profiles = useMemo(
    () => profileOptions(kept, allProfiles),
    [kept, allProfiles],
  );

  const [batch, setBatch] = useState<BatchItem[]>([]);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchNotice, setBatchNotice] = useState<string | null>(null);
  const [addId, setAddId] = useState("");
  const cancelRef = useRef(false);

  // El lote persiste (ids) en este navegador; los PDF viven en el
  // backend por usuario, asi que los links siguen valiendo.
  useEffect(() => {
    const ids = loadBatchIds();
    if (ids.length === 0) return;
    setBatch((prev) => {
      if (prev.length > 0) return prev;
      return ids.map((id) => ({
        jobId: id,
        title: "",
        company: null,
        status: "done" as const,
      }));
    });
  }, []);
  useEffect(() => {
    window.localStorage.setItem(
      BATCH_STORE_KEY,
      JSON.stringify(batch.map((b) => b.jobId)),
    );
  }, [batch]);

  // Titulos del lote desde las guardadas (para ids persistidos).
  const batchWithMeta = useMemo(
    () =>
      batch.map((b) => {
        if (b.title) return b;
        const j = kept.find((k) => String(k.id) === String(b.jobId));
        return j ? { ...b, title: j.title, company: j.company } : b;
      }),
    [batch, kept],
  );

  const setItem = (jobId: string, patch: Partial<BatchItem>) =>
    setBatch((prev) =>
      prev.map((b) =>
        String(b.jobId) === String(jobId) ? { ...b, ...patch } : b,
      ),
    );

  // Genera PDFs adaptados para el filtro actual (máx. 5), en serie.
  const runBatch = async () => {
    if (batchRunning) return;
    const targets = visible.slice(0, MAX_BATCH);
    if (targets.length === 0) {
      setBatchNotice("El filtro actual no tiene ofertas guardadas.");
      return;
    }
    if (visible.length > MAX_BATCH) {
      setBatchNotice(
        `El filtro trae ${visible.length}: se generan las primeras ${MAX_BATCH} (límite anti-saturación).`,
      );
    } else {
      setBatchNotice(null);
    }
    cancelRef.current = false;
    setBatchRunning(true);
    setBatchOpen(true);
    try {
      for (const job of targets) {
        if (cancelRef.current) break;
        setBatch((prev) =>
          prev.some((b) => String(b.jobId) === String(job.id))
            ? prev.map((b) =>
                String(b.jobId) === String(job.id)
                  ? { ...b, status: "working" as const, detail: undefined }
                  : b,
              )
            : [
                ...prev,
                {
                  jobId: String(job.id),
                  title: job.title,
                  company: job.company,
                  status: "working" as const,
                },
              ],
        );
        try {
          await adaptCvAsync(job.id);
          if (cancelRef.current) break;
          setItem(String(job.id), { status: "done", detail: undefined });
        } catch (e) {
          if (cancelRef.current) break;
          setItem(String(job.id), {
            status: "error",
            detail: e instanceof Error ? e.message : "Error generando PDF",
          });
        }
      }
    } finally {
      setBatchRunning(false);
    }
  };

  const stopBatch = () => {
    cancelRef.current = true;
  };

  const removeFromBatch = (jobId: string) =>
    setBatch((prev) => prev.filter((b) => String(b.jobId) !== String(jobId)));

  const addToBatch = (job: Job) => {
    setBatch((prev) =>
      prev.some((b) => String(b.jobId) === String(job.id))
        ? prev
        : [
            ...prev,
            {
              jobId: String(job.id),
              title: job.title,
              company: job.company,
              status: "done" as const,
            },
          ],
    );
    setAddId("");
  };

  // Postulación automática: mueve el lote con PDF listo de
  // Guardadas (kept) a Postulaciones (applied). Sin lógica externa:
  // es el mismo cambio de estado del resto de la app.
  const autoApply = async () => {
    const ready = batchWithMeta.filter((b) => b.status === "done");
    if (ready.length === 0) {
      setBatchNotice(
        "Nada para postular: genera primero los PDF del lote.",
      );
      return;
    }
    if (
      !window.confirm(
        `Mover ${ready.length} oferta(s) con PDF a Postulaciones? ` +
          `Saldrán de Guardadas.`,
      )
    ) {
      return;
    }
    let moved = 0;
    for (const b of ready) {
      try {
        await mutate(b.jobId, {
          status: "applied",
          application_status: "iniciada",
        });
        moved += 1;
      } catch (e) {
        setItem(b.jobId, {
          status: "error",
          detail: e instanceof Error ? e.message : "No se pudo postular",
        });
      }
    }
    reload();
    setBatchNotice(
      moved === ready.length
        ? `${moved} oferta(s) movidas a Postulaciones.`
        : `${moved}/${ready.length} movidas; revisa los errores del lote.`,
    );
  };

  const doneCount = batchWithMeta.filter((b) => b.status === "done").length;
  const addOptions = kept.filter(
    (j) => !batchWithMeta.some((b) => String(b.jobId) === String(j.id)),
  );

  return (
    <>
      <Header
        title="Guardadas"
        subtitle="Ofertas conservadas: genera sus PDF adaptados por filtro (máx. 5 por lote)"
        actions={
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              className="btn btn-primary btn-sm"
              disabled={batchRunning || visible.length === 0}
              onClick={() => void runBatch()}
              title="Genera el PDF adaptado de las ofertas del filtro actual (máximo 5, en serie)"
            >
              <Play size={14} />{" "}
              {batchRunning ? "Generando…" : "Generar PDF automático"}
            </button>
            {batchRunning && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={stopBatch}
                title="Detiene el lote (lo ya generado persiste)"
              >
                <Square size={14} /> Detener
              </button>
            )}
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setBatchOpen((o) => !o)}
              title="Despliega los PDF adaptados generados"
            >
              <FileText size={14} /> PDFs generados ({doneCount})
            </button>
          </div>
        }
      />
      <div className="content">
        {batchOpen && (
          <div className="card" style={{ marginBottom: 16 }}>
            <h3 className="card-title">
              PDFs adaptados generados ({doneCount})
            </h3>
            <p className="card-sub" style={{ marginBottom: 8 }}>
              Quita o agrega postulaciones (incluso de otros filtros). Los
              archivos viven en el backend por usuario.
            </p>
            {batchWithMeta.length === 0 ? (
              <p style={{ margin: 0, fontSize: 13, color: "var(--text-muted)" }}>
                Vacío. Usa “Generar PDF automático” o agrega abajo.
              </p>
            ) : (
              <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
                {batchWithMeta.map((b) => (
                  <li key={b.jobId} style={{ marginBottom: 6 }}>
                    <strong>{b.title || `Oferta ${b.jobId}`}</strong>{" "}
                    {b.company && (
                      <span style={{ color: "var(--text-muted)" }}>
                        · {b.company}
                      </span>
                    )}{" "}
                    {b.status === "working" && <span>⏳ generando…</span>}
                    {b.status === "done" && (
                      <>
                        <a
                          className="btn btn-ghost btn-sm"
                          href={adaptDownloadUrl(b.jobId, "pdf", dlToken)}
                          target="_blank"
                          rel="noreferrer"
                          title="Ver/descargar PDF adaptado"
                        >
                          <Download size={13} /> PDF
                        </a>{" "}
                        <a
                          className="btn btn-ghost btn-sm"
                          href={adaptDownloadUrl(b.jobId, "html", dlToken)}
                          target="_blank"
                          rel="noreferrer"
                          title="Ver HTML adaptado"
                        >
                          HTML
                        </a>
                      </>
                    )}
                    {b.status === "error" && (
                      <span style={{ color: "var(--danger)" }}>
                        ✕ {b.detail ?? "falló"}
                      </span>
                    )}{" "}
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => removeFromBatch(b.jobId)}
                      title="Quitar del lote (el PDF sigue en el backend)"
                    >
                      <Trash2 size={13} /> Quitar
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {addOptions.length > 0 && (
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <select
                  className="select"
                  value={addId}
                  onChange={(e) => setAddId(e.target.value)}
                  style={{ maxWidth: 320 }}
                  title="Agregar una guardada de cualquier filtro"
                >
                  <option value="">Agregar guardada…</option>
                  {addOptions.map((j) => (
                    <option key={j.id} value={String(j.id)}>
                      {j.title} · {j.company || "s/e"}
                    </option>
                  ))}
                </select>
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={!addId}
                  onClick={() => {
                    const j = kept.find((k) => String(k.id) === addId);
                    if (j) addToBatch(j);
                  }}
                >
                  <ListPlus size={14} /> Agregar
                </button>
              </div>
            )}
            <div style={{ marginTop: 10 }}>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => void autoApply()}
                title="Mueve las ofertas del lote con PDF listo de Guardadas a Postulaciones"
              >
                <Send size={14} /> Postulación automática
              </button>
            </div>
          </div>
        )}
        {batchNotice && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>{batchNotice}</p>
          </div>
        )}

        {loading ? (
          <LoadingState label="Cargando guardadas…" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : kept.length === 0 ? (
          <EmptyState
            title="No hay ofertas guardadas."
            hint="Conserva ofertas desde la página de Ofertas y aparecerán aquí para generar sus PDF adaptados."
          />
        ) : (
          <>
            <JobFilters
              value={filters}
              onChange={setFilters}
              companies={companies}
              locations={locations}
              sources={sources}
              profiles={profiles}
            />
            {visible.length === 0 ? (
              <EmptyState
                title="Sin resultados para esos filtros."
                hint="Ajusta la búsqueda o limpia los filtros."
              />
            ) : (
              <div className="job-list">
                {visible.map((j) => (
                  <div key={j.id} className="job-card">
                    <div className="job-card-top">
                      <div className="job-card-main">
                        <h3 className="job-title">
                          <Link to={`/jobs/${j.id}`}>{j.title}</Link>
                        </h3>
                        <div className="job-meta">
                          <span>{j.company || "Empresa no indicada"}</span>
                          {j.location && <span>{j.location}</span>}
                        </div>
                      </div>
                      <MatchBadge score={j.match_score} />
                    </div>
                    <div className="job-card-foot">
                      <button
                        className="btn btn-ghost btn-sm"
                        disabled={batchRunning}
                        onClick={() => {
                          setBatchOpen(true);
                          void (async () => {
                            setBatch((prev) =>
                              prev.some(
                                (b) => String(b.jobId) === String(j.id),
                              )
                                ? prev
                                : [
                                    ...prev,
                                    {
                                      jobId: String(j.id),
                                      title: j.title,
                                      company: j.company,
                                      status: "working" as const,
                                    },
                                  ],
                            );
                            try {
                              await adaptCvAsync(j.id);
                              setItem(String(j.id), { status: "done" });
                            } catch (e) {
                              const err = e as AdaptAsyncError;
                              setItem(String(j.id), {
                                status: "error",
                                detail:
                                  err instanceof Error
                                    ? err.message
                                    : "Error generando PDF",
                              });
                            }
                          })();
                        }}
                        title="Genera su PDF adaptado y lo agrega al lote"
                      >
                        <FileText size={14} /> Generar PDF adaptado
                      </button>
                      <a
                        className="btn btn-ghost btn-sm"
                        href={adaptDownloadUrl(j.id, "pdf", dlToken)}
                        target="_blank"
                        rel="noreferrer"
                        title="Ver/descargar PDF adaptado"
                      >
                        <Download size={14} /> Ver PDF
                      </a>
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
