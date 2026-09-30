import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Download, FileText, RefreshCw } from "lucide-react";
import { Header } from "../components/layout/Header";
import { MatchBadge } from "../components/jobs/MatchBadge";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { useJobs } from "../hooks/useApi";
import {
  cvDownloadUrl,
  fetchCvStatus,
  generateCv,
  type CvStatus,
} from "../services/cv";
import type { Job } from "../types/job";

export function CV() {
  const { data, loading, error, reload } = useJobs("kept");
  const kept = useMemo(() => data ?? [], [data]);
  const [statuses, setStatuses] = useState<Record<string, CvStatus>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshStatus = async (job: Job) => {
    try {
      const st = await fetchCvStatus(job.id);
      setStatuses((s) => ({ ...s, [job.id]: st }));
    } catch {
      /* sin estado: se muestra Generar */
    }
  };

  const runGenerate = async (job: Job, force: boolean) => {
    setBusyId(job.id);
    setNotice(null);
    try {
      const r = await generateCv(job.id, force);
      if (r.decision === "review_required" || r.decision === "below_threshold") {
        setNotice(
          `Oferta "${job.title}": score ${r.match_score} — ${r.decision === "review_required" ? "requiere revisión" : "bajo el umbral"}. ${r.hint ?? ""}`,
        );
      } else {
        await refreshStatus(job);
        setNotice(
          `CV generado para "${job.title}"` +
            (r.pdf_ok ? " (TEX + PDF)." : " (solo TEX: pdflatex no instalado)."),
        );
      }
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Error generando CV");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <Header
        title="CV personalizado"
        subtitle="Un CV por oferta (TEX siempre, PDF si hay compilador)"
      />
      <div className="content">
        <div className="notice-pending">
          <FileText size={15} />
          <span>
            El CV usa <strong>únicamente</strong>{" "}
            <code>backend/data/profiles/base_cv.json</code> (complétalo con
            tus datos reales). Umbrales: score ≥ 75 genera solo, 50–74
            requiere revisión, &lt; 50 no genera salvo forzado.
          </span>
        </div>
        {notice && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>{notice}</p>
          </div>
        )}

        {loading ? (
          <LoadingState label="Cargando ofertas conservadas…" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : kept.length === 0 ? (
          <EmptyState
            title="No hay ofertas conservadas."
            hint="Conserva ofertas desde la página de Ofertas y aparecerán aquí como candidatas para generar su CV."
          />
        ) : (
          <div className="job-list">
            {kept.map((j) => {
              const st = statuses[j.id] ?? (j.cv_generated ? {
                job_id: j.id,
                match_score: j.match_score,
                cv_generated: true,
                tex_path: j.cv_path,
                pdf_path: null,
                download_tex: null,
                download_pdf: null,
              } as CvStatus : undefined);
              return (
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
                    {st?.cv_generated ? (
                      <>
                        <a
                          className="btn btn-ghost btn-sm"
                          href={st.download_tex ?? cvDownloadUrl(j.id, "tex")}
                        >
                          <Download /> TEX
                        </a>
                        <a
                          className="btn btn-ghost btn-sm"
                          href={st.download_pdf ?? cvDownloadUrl(j.id, "pdf")}
                          onClick={(e) => {
                            if (!st.pdf_path && !st.download_pdf) {
                              e.preventDefault();
                              setNotice(
                                "PDF no disponible (pdflatex no instalado). Descarga el TEX.",
                              );
                            }
                          }}
                        >
                          <Download /> PDF
                        </a>
                        <button
                          className="btn btn-ghost btn-sm"
                          disabled={busyId === j.id}
                          onClick={() => runGenerate(j, true)}
                          title="Regenerar (forzado)"
                        >
                          <RefreshCw size={14} /> Regenerar
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          className="btn btn-primary btn-sm"
                          disabled={busyId === j.id || j.match_score === null}
                          onClick={() => runGenerate(j, false)}
                          title={
                            j.match_score === null
                              ? "Analiza la oferta primero (botón Analizar en el detalle)"
                              : "Genera según umbrales (POST /jobs/{id}/cv)"
                          }
                        >
                          <FileText />{" "}
                          {busyId === j.id ? "Generando…" : "Generar CV"}
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          disabled={busyId === j.id || j.match_score === null}
                          onClick={() => runGenerate(j, true)}
                          title="Forzar generación aunque el score esté bajo revisión"
                        >
                          Forzar
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
