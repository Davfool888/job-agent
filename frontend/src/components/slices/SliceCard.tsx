import { Link } from "react-router-dom";
import {
  Building2,
  ChevronDown,
  ExternalLink,
  Globe,
  MapPin,
} from "lucide-react";
import type { Job, JobAnalysis } from "../../types/job";
import { sourceLabel } from "../../utils/constants";
import { formatDate, timeAgo } from "../../utils/format";
import { referenceDate } from "../../utils/jobs";
import { MatchBadge } from "../jobs/MatchBadge";
import { StatusBadge } from "../jobs/StatusBadge";

export type SliceExit = "left" | "right" | "up" | null;

interface Props {
  job: Job;
  dragX: number;
  dragY: number;
  dragging: boolean;
  exiting: SliceExit;
  expanded: boolean;
  analysis: JobAnalysis | null;
  analysisLoading: boolean;
  onToggleExpand: () => void;
}

export function SliceCard({
  job,
  dragX,
  dragY,
  dragging,
  exiting,
  expanded,
  analysis,
  analysisLoading,
  onToggleExpand,
}: Props) {
  const rotate = dragX * 0.06;
  const showKeep = dragX > 40 || exiting === "right";
  const showDrop = dragX < -40 || exiting === "left";
  const showApply = dragY < -50 || exiting === "up";

  const style: React.CSSProperties = exiting
    ? {
        transform:
          exiting === "up"
            ? "translateY(-480px) scale(0.95)"
            : `translateX(${exiting === "right" ? 480 : -480}px) rotate(${exiting === "right" ? 18 : -18}deg)`,
        opacity: 0,
        transition: "transform 0.22s ease-in, opacity 0.22s ease-in",
      }
    : {
        transform: `translate(${dragX}px, ${dragY}px) rotate(${rotate}deg)`,
        transition: dragging ? "none" : "transform 0.18s ease-out",
        cursor: dragging ? "grabbing" : "grab",
      };

  return (
    <article
      className="slice-card"
      style={style}
      data-expanded={expanded}
      aria-label={`${job.title} en ${job.company ?? "empresa no indicada"}`}
    >
      <div className={`slice-stamp slice-stamp-keep${showKeep ? " on" : ""}`}>
        GUARDAR
      </div>
      <div className={`slice-stamp slice-stamp-drop${showDrop ? " on" : ""}`}>
        DESCARTAR
      </div>
      <div className={`slice-stamp slice-stamp-up${showApply ? " on" : ""}`}>
        POSTULARME
      </div>

      <div className="slice-top">
        <span className="badge badge-source">
          <Globe /> {sourceLabel(job.source)}
        </span>
        <MatchBadge score={job.match_score} />
        <StatusBadge status={job.status} />
      </div>

      <h3 className="slice-title">{job.title}</h3>
      <div className="slice-meta">
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
        <span title={job.published_text || "Fecha en que se encontró"}>
          Publicada {timeAgo(referenceDate(job)) || formatDate(referenceDate(job))}
        </span>
      </div>

      <div className={`slice-desc${expanded ? " full" : ""}`}>
        {job.description
          ? expanded
            ? job.description
            : job.description.slice(0, 220) +
              (job.description.length > 220 ? "…" : "")
          : "Sin descripción disponible."}
      </div>

      {expanded && (
        <div className="slice-details">
          <dl className="kv">
            <dt>Plataforma</dt>
            <dd>{sourceLabel(job.source)}</dd>
            <dt>Empresa</dt>
            <dd>{job.company ?? "—"}</dd>
            <dt>Ubicación</dt>
            <dd>{job.location ?? "—"}</dd>
            <dt>Rol detectado</dt>
            <dd>{job.detected_role ?? "—"}</dd>
            <dt>Categoría</dt>
            <dd>{job.category ?? "—"}</dd>
            <dt>Experiencia</dt>
            <dd>{job.experience_required ?? "—"}</dd>
            {job.search_query && (
              <>
                <dt>Búsqueda</dt>
                <dd>{job.search_query}</dd>
              </>
            )}
          </dl>
          {analysisLoading && (
            <p className="slice-sub">Analizando compatibilidad…</p>
          )}
          {!analysisLoading && analysis?.fit_report && (
            <div className="slice-fit">
              <p className="slice-sub">
                Compatibilidad: {analysis.fit_report.label}
                {typeof analysis.fit_report.score === "number"
                  ? ` (${Math.round(analysis.fit_report.score)}%)`
                  : ""}
              </p>
              {analysis.fit_report.strengths.slice(0, 2).map((s) => (
                <p key={s} className="slice-fit-ok">
                  ✓ {s}
                </p>
              ))}
              {analysis.fit_report.gaps.slice(0, 2).map((g) => (
                <p key={g} className="slice-fit-bad">
                  • {g}
                </p>
              ))}
            </div>
          )}
          {job.matched_skills.length > 0 && (
            <>
              <p className="slice-sub">Skills coincidentes</p>
              <div className="skill-chips">
                {job.matched_skills.map((s) => (
                  <span key={s} className="chip">
                    {s}
                  </span>
                ))}
              </div>
            </>
          )}
          {job.missing_skills.length > 0 && (
            <>
              <p className="slice-sub">Skills faltantes</p>
              <div className="skill-chips">
                {job.missing_skills.map((s) => (
                  <span key={s} className="chip chip-missing">
                    {s}
                  </span>
                ))}
              </div>
            </>
          )}
          {job.evidence.length > 0 && (
            <>
              <p className="slice-sub">Evidencia</p>
              <div className="skill-chips">
                {job.evidence.slice(0, 8).map((e) => (
                  <span key={e} className="chip chip-neutral">
                    {e}
                  </span>
                ))}
              </div>
            </>
          )}
          <div className="slice-links">
            <Link className="btn btn-ghost btn-sm" to={`/jobs/${job.id}`}>
              Ver oferta
            </Link>
            <a
              className="btn btn-ghost btn-sm"
              href={job.url}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink /> Ir a oferta
            </a>
          </div>
        </div>
      )}

      <button
        type="button"
        className="btn btn-ghost btn-sm slice-more"
        onClick={onToggleExpand}
        aria-expanded={expanded}
      >
        <ChevronDown className={expanded ? "chev open" : "chev"} />
        {expanded ? "Ver menos" : "Desliza abajo o toca para ver más"}
      </button>
    </article>
  );
}
