import { useMemo, useState } from "react";
import { Header } from "../components/layout/Header";
import { JobCard } from "../components/jobs/JobCard";
import { JobFilters } from "../components/jobs/JobFilters";
import { DEFAULT_FILTERS } from "../types/filters";
import type { JobFilterState } from "../types/filters";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { useJobs } from "../hooks/useApi";
import { formatDateTime } from "../utils/format";
import { applyJobFilters, uniqueSorted } from "../utils/jobs";

export function Discarded() {
  const { data, loading, error, reload, mutate } = useJobs("discarded");
  const [filters, setFilters] = useState<JobFilterState>(DEFAULT_FILTERS);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const all = useMemo(() => data ?? [], [data]);
  const visible = useMemo(() => applyJobFilters(all, filters), [all, filters]);

  const companies = useMemo(() => uniqueSorted(all, (j) => j.company), [all]);
  const locations = useMemo(() => uniqueSorted(all, (j) => j.location), [all]);
  const sources = useMemo(() => uniqueSorted(all, (j) => j.source), [all]);

  const recover = async (id: string) => {
    setBusyId(id);
    setActionError(null);
    try {
      await mutate(id, { status: "new" });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Error inesperado");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <Header
        title="Ofertas descartadas"
        subtitle={`${all.length} descartadas (se conservan todos sus datos)`}
      />
      <div className="content">
        {actionError && <div className="alert-error">{actionError}</div>}
        {loading ? (
          <LoadingState label="Cargando descartadas…" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : all.length === 0 ? (
          <EmptyState
            title="No hay ofertas descartadas."
            hint="Cuando descartes una oferta aparecerá aquí con su motivo."
          />
        ) : (
          <>
            <JobFilters
              value={filters}
              onChange={setFilters}
              companies={companies}
              locations={locations}
              sources={sources}
            />
            {visible.length === 0 ? (
              <EmptyState title="Sin resultados para esos filtros." />
            ) : (
              <div className="job-list">
                {visible.map((job) => (
                  <div key={job.id}>
                    <JobCard
                      job={job}
                      busy={busyId === job.id}
                      onKeep={() => recover(job.id)}
                      onDiscard={() => {}}
                      onRecover={() => recover(job.id)}
                      showRecover
                    />
                    <div
                      className="card"
                      style={{
                        marginTop: -6,
                        borderTop: "none",
                        borderTopLeftRadius: 0,
                        borderTopRightRadius: 0,
                        paddingTop: 10,
                        fontSize: 12.5,
                        color: "var(--text-muted)",
                      }}
                    >
                      Motivo: <strong>{job.discard_reason ?? "—"}</strong>
                      {job.discard_note && <> · “{job.discard_note}”</>}
                      <> · Decidida: {formatDateTime(job.decided_at)}</>
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
