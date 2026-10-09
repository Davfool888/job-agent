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
  const { data, loading, error, reload } = useJobs("applied");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [stageError, setStageError] = useState<string | null>(null);
  const [sort, setSort] = useState<"recent" | "match_desc" | "match_asc">("recent");

  const applied = useMemo(() => {
    const list = [...(data ?? [])];
    if (sort === "match_desc") {
      list.sort(
        (a, b) => (b.match_score ?? -1) - (a.match_score ?? -1) || Number(b.id) - Number(a.id),
      );
    } else if (sort === "match_asc") {
      list.sort(
        (a, b) => (a.match_score ?? 101) - (b.match_score ?? 101) || Number(b.id) - Number(a.id),
      );
    } else {
      list.sort((a, b) => Number(b.id) - Number(a.id));
    }
    return list;
  }, [data, sort]);

  const setStage = async (id: string, stage: string) => {
    setBusyId(id);
    setStageError(null);
    try {
      await updateJobStatus(id, { status: "applied", application_status: stage });
      reload();
    } catch (e) {
      setStageError(e instanceof Error ? e.message : "No se pudo cambiar la etapa");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <Header
        title="Postulaciones"
        subtitle="Ofertas con postulación iniciada. Las vistas sin postular viven en Vistas."
      />
      <div className="content">
        {stageError && <div className="alert-error">{stageError}</div>}
        {applied.length > 0 && !loading && !error && (
          <div className="toolbar" style={{ marginBottom: 12 }}>
            <div className="toolbar-row">
              <select
                className="select"
                value={sort}
                onChange={(e) =>
                  setSort(e.target.value as "recent" | "match_desc" | "match_asc")
                }
                title="Ordenar por coincidencia con tu perfil"
              >
                <option value="recent">Más recientes</option>
                <option value="match_desc">Mayor coincidencia</option>
                <option value="match_asc">Menor coincidencia</option>
              </select>
            </div>
          </div>
        )}
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
