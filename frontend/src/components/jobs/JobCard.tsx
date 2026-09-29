import { Link } from "react-router-dom";
import {
  Archive,
  BookmarkCheck,
  Building2,
  Copy,
  ExternalLink,
  Globe,
  MapPin,
  RotateCcw,
  Send,
} from "lucide-react";
import type { Job } from "../../types/job";
import { sourceLabel } from "../../utils/constants";
import { formatDate, timeAgo } from "../../utils/format";
import { referenceDate } from "../../utils/jobs";
import { MatchBadge } from "./MatchBadge";
import { StatusBadge } from "./StatusBadge";

interface Props {
  job: Job;
  busy?: boolean;
  onKeep: (job: Job) => void;
  onDiscard: (job: Job) => void;
  onRecover?: (job: Job) => void;
  onApply?: (job: Job) => void;
  showRecover?: boolean;
}

export function JobCard({
  job,
  busy,
  onKeep,
  onDiscard,
  onRecover,
  onApply,
  showRecover,
}: Props) {
  return (
    <article className="job-card">
      <div className="job-card-top">
        <div className="job-card-main">
          <h3 className="job-title">
            <Link to={`/jobs/${job.id}`}>{job.title}</Link>
          </h3>
          <div className="job-meta">
            {job.company && (
              <span>
                <Building2 /> {job.company}
              </span>
            )}
            {job.location && (
              <span>
                <MapPin /> {job.location}
              </span>
            )}
            <span>Encontrada en {sourceLabel(job.source)}</span>
            <span title={job.published_text || "Fecha en que se encontró"}>
              Publicada {timeAgo(referenceDate(job)) || formatDate(referenceDate(job))}
              {job.published_at ? "" : " (aprox.)"}
            </span>
            {job.search_query && <span>Búsqueda: {job.search_query}</span>}
          </div>
          {job.description && (
            <p className="job-desc">{job.description.slice(0, 220)}</p>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
          <span className="badge badge-source" title={`Oferta encontrada en ${sourceLabel(job.source)}`}>
            <Globe /> {sourceLabel(job.source)}
          </span>
          {(job.times_seen ?? 1) > 1 && (
            <span
              className="badge badge-match-mid"
              title={`Esta misma oferta (mismo cargo y empresa) apareció ${job.times_seen} veces con distintas publicaciones. Sirve para detectar republicaciones que simulan ser nuevas.`}
            >
              <Copy /> ×{job.times_seen} republicada
            </span>
          )}
          <MatchBadge score={job.match_score} />
          <StatusBadge status={job.status} />
          {job.detected_role && job.category !== "OTHER" && (
            <span
              className="badge badge-match"
              title={`Rol detectado por contenido (no por el título): ${job.detected_role}`}
            >
              Rol: {job.detected_role}
            </span>
          )}
        </div>
      </div>

      <div className="job-card-foot">
        <Link className="btn btn-ghost btn-sm" to={`/jobs/${job.id}`}>
          Ver oferta
        </Link>
        <a
          className="btn btn-ghost btn-sm"
          href={job.url}
          target="_blank"
          rel="noreferrer"
          onClick={() => onApply?.(job)}
          title={`Abre la oferta original en ${sourceLabel(job.source)}`}
        >
          <ExternalLink /> Ir a oferta
        </a>
        <span className="spacer" />
        {showRecover && onRecover ? (
          <button
            className="btn btn-primary btn-sm"
            disabled={busy}
            onClick={() => onRecover(job)}
          >
            <RotateCcw /> Recuperar
          </button>
        ) : (
          <>
            {job.status !== "kept" && (
              <button
                className="btn btn-success btn-sm"
                disabled={busy}
                onClick={() => onKeep(job)}
              >
                <BookmarkCheck /> Conservar
              </button>
            )}
            {job.status === "kept" && onApply && (
              <button
                className="btn btn-primary btn-sm"
                disabled={busy}
                onClick={() => onApply(job)}
              >
                <Send /> Postularme
              </button>
            )}
            {job.status !== "discarded" && (
              <button
                className="btn btn-danger-ghost btn-sm"
                disabled={busy}
                onClick={() => onDiscard(job)}
              >
                <Archive /> Descartar
              </button>
            )}
          </>
        )}
      </div>
    </article>
  );
}
