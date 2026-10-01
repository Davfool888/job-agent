import { useEffect, useMemo, useState } from "react";
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
import { useJobs, useProfileOptions } from "../hooks/useApi";
import { fetchJobsSince } from "../services/searchProfiles";
import type { Job } from "../types/job";
import { applyJobFilters, profileOptions, uniqueSorted } from "../utils/jobs";

export function Jobs() {
  // Excluye descartadas: esas viven en /discarded.
  const { data, loading, error, reload, mutate } = useJobs();
  const allProfiles = useProfileOptions();
  const [filters, setFilters] = useState<JobFilterState>(DEFAULT_FILTERS);
  const [discarding, setDiscarding] = useState<Job | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [newCount, setNewCount] = useState<number | null>(null);

  // "N nuevas desde tu ultima visita": usa GET /jobs?since= con la marca
  // guardada localmente (solo preferencia visual, los datos son del backend).
  useEffect(() => {
    let alive = true;
    const lastVisit = window.localStorage.getItem("jobagent_last_visit");
    if (lastVisit) {
      fetchJobsSince(lastVisit)
        .then((jobs) => {
          if (alive) setNewCount(jobs.filter((j) => j.status !== "discarded").length);
        })
        .catch(() => {
          if (alive) setNewCount(null);
        });
    } else {
      setNewCount(0);
    }
    window.localStorage.setItem("jobagent_last_visit", new Date().toISOString());
    return () => {
      alive = false;
    };
  }, []);

  const active = useMemo(
    () => (data ?? []).filter((j) => j.status !== "discarded"),
    [data],
  );

  const visible = useMemo(() => applyJobFilters(active, filters), [active, filters]);

  const companies = useMemo(() => uniqueSorted(active, (j) => j.company), [active]);
  const locations = useMemo(() => uniqueSorted(active, (j) => j.location), [active]);
  const sources = useMemo(() => uniqueSorted(active, (j) => j.source), [active]);
  const profiles = useMemo(
    () => profileOptions(active, allProfiles),
    [active, allProfiles],
  );

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
    // "Ir a oferta": abrir la URL registra la vista (pasa a Vistas).
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
        {newCount !== null && newCount > 0 && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>
              ✨ <strong>{newCount} nuevas</strong> desde tu última visita
              (traídas por la búsqueda automática).{" "}
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setFilters({ ...filters, sort: "found" })}
              >
                Ver recientes
              </button>
            </p>
          </div>
        )}
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
              profiles={profiles}
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
