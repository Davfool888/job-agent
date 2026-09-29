import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Archive,
  ArrowLeft,
  BookmarkCheck,
  Building2,
  ExternalLink,
  MapPin,
  Send,
  Target,
} from "lucide-react";
import { Header } from "../components/layout/Header";
import { DiscardModal } from "../components/jobs/DiscardModal";
import { MatchBadge } from "../components/jobs/MatchBadge";
import { StatusBadge } from "../components/jobs/StatusBadge";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { useJob, useJobExtra } from "../hooks/useApi";
import { analyzeJob, updateJobStatus } from "../services/jobs";
import type { Job } from "../types/job";
import { formatDate, formatDateTime, timeAgo } from "../utils/format";

export function JobDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const jobId = Number(id);
  const job = useJob(jobId);
  const extra = useJobExtra(jobId);
  const [discarding, setDiscarding] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutate = async (payload: Parameters<typeof updateJobStatus>[1]) => {
    setBusy(true);
    setError(null);
    try {
      await updateJobStatus(jobId, payload);
      job.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error inesperado");
    } finally {
      setBusy(false);
    }
  };

  const apply = async (j: Job) => {
    await mutate({ status: "applied", application_status: "iniciada" });
    window.open(j.url, "_blank", "noopener");
    navigate("/applications");
  };

  const analyze = async () => {
    setBusy(true);
    setError(null);
    try {
      await analyzeJob(jobId);
      job.reload();
      extra.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error inesperado");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Header
        title="Detalle de oferta"
        actions={
          <Link className="btn btn-ghost btn-sm" to="/jobs">
            <ArrowLeft /> Volver
          </Link>
        }
      />
      <div className="content">
        {error && <div className="alert-error">{error}</div>}
        {Number.isNaN(jobId) ? (
          <EmptyState title="ID de oferta inválido." />
        ) : job.loading ? (
          <LoadingState label="Cargando oferta…" />
        ) : job.error || !job.data ? (
          <ErrorState message={job.error ?? "Oferta no encontrada."} onRetry={job.reload} />
        ) : (
          <DetailBody
            job={job.data}
            extraDesc={extra.data?.description ?? null}
            extraTags={extra.data?.tags ?? []}
            extraReqs={extra.data?.requirements ?? []}
            extraSkills={extra.data?.skills ?? []}
            busy={busy}
            onKeep={() => mutate({ status: "kept" })}
            onDiscard={() => setDiscarding(job.data)}
            onApply={() => job.data && apply(job.data)}
            onAnalyze={analyze}
          />
        )}
      </div>
      <DiscardModal
        job={discarding}
        saving={busy}
        onClose={() => setDiscarding(null)}
        onConfirm={async (reason, note) => {
          await mutate({
            status: "discarded",
            discard_reason: reason,
            discard_note: note || null,
          });
          setDiscarding(null);
        }}
      />
    </>
  );
}

function DetailBody({
  job,
  extraDesc,
  extraTags,
  extraReqs,
  extraSkills,
  busy,
  onKeep,
  onDiscard,
  onApply,
  onAnalyze,
}: {
  job: Job;
  extraDesc: string | null;
  extraTags: string[];
  extraReqs: string[];
  extraSkills: string[];
  busy: boolean;
  onKeep: () => void;
  onDiscard: () => void;
  onApply: () => void;
  onAnalyze: () => void;
}) {
  const description = extraDesc || job.description;

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
          <div style={{ flex: 1 }}>
            <h2 className="section-title">{job.title}</h2>
            <div className="job-meta">
              {job.company && (
                <span>
                  <Building2 size={13} /> {job.company}
                </span>
              )}
              {job.location && (
                <span>
                  <MapPin size={13} /> {job.location}
                </span>
              )}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
            <MatchBadge score={job.match_score} />
            <StatusBadge status={job.status} />
          </div>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
          {job.status !== "kept" && job.status !== "discarded" && (
            <button className="btn btn-success btn-sm" disabled={busy} onClick={onKeep}>
              <BookmarkCheck /> Conservar
            </button>
          )}
          {job.status !== "discarded" && (
            <button className="btn btn-danger-ghost btn-sm" disabled={busy} onClick={onDiscard}>
              <Archive /> Descartar
            </button>
          )}
          <button className="btn btn-primary btn-sm" disabled={busy} onClick={onApply}>
            <Send /> Postularme
          </button>
          {job.match_score === null && (
            <button
              className="btn btn-ghost btn-sm"
              disabled={busy}
              onClick={onAnalyze}
              title="Analiza título + descripción con reglas (POST /jobs/{id}/analyze)"
            >
              <Target /> Analizar
            </button>
          )}
          <a className="btn btn-ghost btn-sm" href={job.url} target="_blank" rel="noreferrer">
            <ExternalLink /> Ir a oferta laboral
          </a>
        </div>
      </div>

      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <h3 className="card-title">Información general</h3>
          <dl className="kv" style={{ marginTop: 10 }}>
            <dt>Empresa</dt>
            <dd>{job.company || "—"}</dd>
            <dt>Ubicación</dt>
            <dd>{job.location || "—"}</dd>
            <dt>Fuente</dt>
            <dd>{job.source}</dd>
            <dt>Búsqueda</dt>
            <dd>{job.search_query || "—"}</dd>
            {job.discovered_by && job.discovered_by.length > 0 && (
              <>
                <dt>Descubierta por</dt>
                <dd>{job.discovered_by.join(", ")}</dd>
              </>
            )}
            <dt>Encontrada</dt>
            <dd>{formatDate(job.created_at)}</dd>
            <dt>Publicada</dt>
            <dd title={job.published_text ?? undefined}>
              {job.published_at
                ? `${formatDateTime(job.published_at)} (${timeAgo(job.published_at)})`
                : "Fecha no provista por la fuente"}
            </dd>
            {(job.times_seen ?? 1) > 1 && (
              <>
                <dt>Republicación</dt>
                <dd>
                  Esta oferta apareció <strong>×{job.times_seen}</strong> con
                  distintas publicaciones (posible republicación para
                  parecer nueva).
                </dd>
              </>
            )}
            <dt>Decisión</dt>
            <dd>
              {job.status === "new"
                ? "Sin decidir"
                : `${job.status} · ${formatDateTime(job.decided_at)}`}
            </dd>
            {job.status === "discarded" && (
              <>
                <dt>Motivo</dt>
                <dd>
                  {job.discard_reason ?? "—"}
                  {job.discard_note ? ` — “${job.discard_note}”` : ""}
                </dd>
              </>
            )}
            {job.status === "applied" && (
              <>
                <dt>Postulación</dt>
                <dd>
                  {job.application_status ?? "iniciada"} ·{" "}
                  {formatDateTime(job.applied_at)}
                </dd>
              </>
            )}
          </dl>
        </div>

        <div className="card">
          <h3 className="card-title">Análisis de coincidencia</h3>
          {job.match_score === null ? (
            <div className="notice-pending" style={{ marginTop: 10 }}>
              <span>
                Sin analizar. El backend puede analizar título + descripción
                con reglas determinísticas (sin IA de pago) y detectar el
                rol real aunque el título no sea de datos.
              </span>
            </div>
          ) : (
            <div style={{ marginTop: 10 }}>
              <p style={{ fontSize: 26, fontWeight: 700, margin: "0 0 8px" }}>
                {Math.round(job.match_score)}%
              </p>
              {job.detected_role && job.category !== "OTHER" && (
                <p style={{ margin: "0 0 8px", fontSize: 13 }}>
                  Rol detectado: <strong>{job.detected_role}</strong>
                  {job.experience_required
                    ? ` · Experiencia: ${job.experience_required}`
                    : ""}
                </p>
              )}
              {job.evidence && job.evidence.length > 0 && (
                <>
                  <p className="card-sub">Evidencia</p>
                  <div className="skill-chips">
                    {job.evidence.map((e) => (
                      <span key={e} className="chip chip-neutral">
                        {e}
                      </span>
                    ))}
                  </div>
                </>
              )}
              <p className="card-sub" style={{ marginTop: 10 }}>
                Coincidentes
              </p>
              <div className="skill-chips">
                {job.matched_skills.length === 0 && <span className="chip chip-neutral">—</span>}
                {job.matched_skills.map((s) => (
                  <span key={s} className="chip">
                    {s} ✓
                  </span>
                ))}
              </div>
              <p className="card-sub" style={{ marginTop: 10 }}>
                Faltantes
              </p>
              <div className="skill-chips">
                {job.missing_skills.length === 0 && <span className="chip chip-neutral">—</span>}
                {job.missing_skills.map((s) => (
                  <span key={s} className="chip chip-missing">
                    {s} ✕
                  </span>
                ))}
              </div>
            </div>
          )}
          {(extraTags.length > 0 || extraSkills.length > 0) && (
            <>
              <p className="card-sub" style={{ marginTop: 12 }}>
                Detectado en la oferta (scraper)
              </p>
              <div className="skill-chips">
                {[...extraTags, ...extraSkills].slice(0, 12).map((t) => (
                  <span key={t} className="chip chip-neutral">
                    {t}
                  </span>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      <h3 className="section-title">Descripción original</h3>
      {description ? (
        <div className="desc-block">{description}</div>
      ) : (
        <div className="state-box">
          <p style={{ margin: 0 }}>Sin descripción guardada.</p>
        </div>
      )}

      {extraReqs.length > 0 && (
        <>
          <h3 className="section-title" style={{ marginTop: 18 }}>
            Requisitos detectados
          </h3>
          <div className="card">
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13.5 }}>
              {extraReqs.map((r) => (
                <li key={r} style={{ marginBottom: 5 }}>
                  {r}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </>
  );
}
