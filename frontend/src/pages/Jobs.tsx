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

export function Jobs() {
  // Excluye descartadas: esas viven en /discarded.
  const { data, loading, error, reload, mutate } = useJobs();
  const [filters, setFilters] = useState<JobFilterState>(DEFAULT_FILTERS);
  const [discarding, setDiscarding] = useState<Job | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const active = useMemo(
    () => (data ?? []).filter((j) => j.status !== "discarded"),
    [data],
  );

  const visible = useMemo(() => applyJobFilters(active, filters), [active, filters]);

  const companies = useMemo(() => uniqueSorted(active, (j) => j.company), [active]);
  const locations = useMemo(() => uniqueSorted(active, (j) => j.location), [active]);
  const sources = useMemo(() => uniqueSorted(active, (j) => j.source), [active]);

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
    // "Ir a oferta": abrir la URL no es postularse; se registra como abierta.
    if (job.status === "new" || job.status === "kept") {
      void mutate(job.id, { status: "opened" });
    }
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
        title="Ofertas"
        subtitle={`${active.length} ofertas activas (sin descartadas)`}
      />
      <div className="content">
        {actionError && <div className="alert-error">{actionError}</div>}
        {loading ? (
          <LoadingState label="Cargando ofertas…" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : active.length === 0 ? (
          <EmptyState
            title="No hay ofertas disponibles."
            hint="Usa «Buscar nuevas ofertas» en el Dashboard para traer ofertas de Computrabajo."
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
              <EmptyState
                title="Sin resultados para esos filtros."
                hint="Ajusta la búsqueda o limpia los filtros."
              />
            ) : (
              <div className="job-list">
                {visible.map((job) => (
                  <JobCard
                    key={job.id}
                    job={job}
                    busy={busyId === job.id}
                    onKeep={keep}
                    onDiscard={setDiscarding}
                    onApply={job.status === "kept" ? apply : openOriginal}
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
