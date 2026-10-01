import { useMemo, useState } from "react";
import { Header } from "../components/layout/Header";
import { DiscardModal } from "../components/jobs/DiscardModal";
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
import type { Job } from "../types/job";
import { applyJobFilters, uniqueSorted } from "../utils/jobs";

export function Viewed() {
  const { data, loading, error, reload, mutate } = useJobs("opened");
  const [filters, setFilters] = useState<JobFilterState>(DEFAULT_FILTERS);
  const [discarding, setDiscarding] = useState<Job | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const all = useMemo(() => data ?? [], [data]);
  const visible = useMemo(() => applyJobFilters(all, filters), [all, filters]);

  const companies = useMemo(() => uniqueSorted(all, (j) => j.company), [all]);
  const locations = useMemo(() => uniqueSorted(all, (j) => j.location), [all]);
  const sources = useMemo(() => uniqueSorted(all, (j) => j.source), [all]);

  const run = async (job: Job, fn: () => Promise<unknown>) => {
    setBusyId(job.id);
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Error inesperado");
    } finally {
      setBusyId(null);
    }
  };

  const keep = (job: Job) => run(job, () => mutate(job.id, { status: "kept" }));

  const apply = (job: Job) =>
    run(job, async () => {
      await mutate(job.id, { status: "applied", application_status: "iniciada" });
      window.open(job.url, "_blank", "noopener");
    });

  const openOriginal = (job: Job) => {
    window.open(job.url, "_blank", "noopener");
  };

  const confirmDiscard = async (reason: string, note: string) => {
    if (!discarding) return;
    const job = discarding;
    setBusyId(job.id);
    try {
      await mutate(job.id, {
        status: "discarded",
        discard_reason: reason,
        discard_note: note || null,
      });
      setDiscarding(null);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Error inesperado");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <Header
        title="Vistas"
        subtitle={`${all.length} ofertas visualizadas (abriste la oferta original o el detalle)`}
      />
      <div className="content">
        {actionError && <div className="alert-error">{actionError}</div>}
        {loading ? (
          <LoadingState label="Cargando vistas…" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : all.length === 0 ? (
          <EmptyState
            title="No hay ofertas vistas."
            hint="Cuando abras una oferta (Ver oferta / Ir a oferta) aparecerá aquí. Si la descartas, pasa a Descartadas."
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
                  <JobCard
                    key={job.id}
                    job={job}
                    busy={busyId === job.id}
                    onKeep={keep}
                    onDiscard={setDiscarding}
                    onApply={apply}
                    onOpen={openOriginal}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
      <DiscardModal
        job={discarding}
        saving={busyId === discarding?.id}
        onClose={() => setDiscarding(null)}
        onConfirm={confirmDiscard}
      />
    </>
  );
}
