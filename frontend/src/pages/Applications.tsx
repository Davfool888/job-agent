import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { Header } from "../components/layout/Header";
import { StatusBadge } from "../components/jobs/StatusBadge";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { useJobs } from "../hooks/useApi";
import { APPLICATION_STATUSES } from "../utils/constants";
import { formatDateTime } from "../utils/format";
import { updateJobStatus } from "../services/jobs";

export function Applications() {
  const { data, loading, error, reload } = useJobs();
  const [busyId, setBusyId] = useState<number | null>(null);

  const applied = useMemo(
    () => (data ?? []).filter((j) => j.status === "applied" || j.status === "opened"),
    [data],
  );

  const setStage = async (id: number, stage: string) => {
    setBusyId(id);
    try {
      await updateJobStatus(id, { status: "applied", application_status: stage });
      reload();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <Header
        title="Postulaciones"
        subtitle="Ofertas abiertas o con postulación iniciada. Abrir la URL registra el interés, no la postulación completada."
      />
      <div className="content">
        {loading ? (
          <LoadingState label="Cargando postulaciones…" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : applied.length === 0 ? (
          <EmptyState
            title="Aún no hay postulaciones."
            hint="Desde una oferta usa «Postularme»: se abrirá la oferta original y quedará registrada aquí."
          />
        ) : (
          <div className="job-list">
            {applied.map((j) => (
              <div key={j.id} className="job-card">
                <div className="job-card-top">
                  <div className="job-card-main">
                    <h3 className="job-title">
                      <Link to={`/jobs/${j.id}`}>{j.title}</Link>
                    </h3>
                    <div className="job-meta">
                      <span>{j.company || "Empresa no indicada"}</span>
                      {j.location && <span>{j.location}</span>}
                      <span>Iniciada: {formatDateTime(j.applied_at)}</span>
                    </div>
                  </div>
                  <StatusBadge status={j.status} />
                </div>
                <div className="job-card-foot">
                  <a
                    className="btn btn-ghost btn-sm"
                    href={j.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <ExternalLink /> Abrir oferta
                  </a>
                  <span className="spacer" />
                  <label style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
                    Etapa:{" "}
                    <select
                      className="select"
                      disabled={busyId === j.id}
                      value={j.application_status ?? "iniciada"}
                      onChange={(e) => setStage(j.id, e.target.value)}
                    >
                      {APPLICATION_STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
