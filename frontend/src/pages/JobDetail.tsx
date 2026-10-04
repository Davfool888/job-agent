import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Archive,
  ArrowLeft,
  BookmarkCheck,
  Building2,
  Download,
  ExternalLink,
  Eye,
  FileText,
  MapPin,
  RefreshCw,
  Send,
  Sparkles,
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
import {
  ADAPT_STAGES,
  adaptCvAsync,
  adaptDownloadUrl,
  adaptErrorMessage,
  type AdaptAsyncError,
  type AdaptCvResult,
} from "../services/adapt";
import { API_URL } from "../services/api";
import {
  fetchCustomizedCv,
  generateCv,
  type CustomizedCv,
} from "../services/cv";
import type { Job } from "../types/job";
import { formatDate, formatDateTime, timeAgo } from "../utils/format";

export function JobDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const jobId = id ?? "";
  const job = useJob(jobId);
  const extra = useJobExtra(jobId);
  const [discarding, setDiscarding] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profileIncomplete, setProfileIncomplete] = useState<{ message: string } | null>(null);

  // Visualizar el detalle registra la vista: new -> opened (pasa a Vistas).
  // kept se conserva para no perder "guardadas".
  useEffect(() => {
    if (job.data && job.data.status === "new") {
      updateJobStatus(jobId, { status: "opened" })
        .then(() => job.reload())
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.data?.status]);

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
    // Abrir PRIMERO: si va despues del await, el bloqueador de popups
    // lo intercepta porque pierde el gesto del usuario.
    window.open(j.url, "_blank", "noopener");
    await mutate({ status: "applied", application_status: "iniciada" });
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

  const [adapt, setAdapt] = useState<AdaptCvResult | null>(null);
  const [adapting, setAdapting] = useState(false);
  const [adaptStage, setAdaptStage] = useState<string | null>(null);

  const [cvView, setCvView] = useState<{
    phase: "loading" | "ready" | "error";
    data?: CustomizedCv;
    error?: string;
  } | null>(null);
  const [generating, setGenerating] = useState(false);

  const showCv = async () => {
    setCvView({ phase: "loading" });
    setError(null);
    try {
      const data = await fetchCustomizedCv(jobId);
      setCvView({ phase: "ready", data });
    } catch (e) {
      setCvView({
        phase: "error",
        error: e instanceof Error ? e.message : "Error inesperado",
      });
    }
  };

  const generate = async (force: boolean) => {
    setGenerating(true);
    setError(null);
    try {
      await generateCv(jobId, force);
      const data = await fetchCustomizedCv(jobId);
      setCvView({ phase: "ready", data });
      job.reload();
    } catch (e) {
      setCvView({
        phase: "error",
        error: e instanceof Error ? e.message : "Error inesperado",
      });
    } finally {
      setGenerating(false);
    }
  };

  const runAdapt = async () => {
    if (adapting) return;
    setAdapting(true);
    setAdaptStage(ADAPT_STAGES[0]);
    setError(null);
    setProfileIncomplete(null);
    // Polling asincrono: el POST /start responde en ms y el PDF se genera
    // en fondo. Las etapas rotan por tiempo y por polls para feedback real.
    let stage = 0;
    const timer = window.setInterval(() => {
      stage = Math.min(stage + 1, ADAPT_STAGES.length - 1);
      setAdaptStage(ADAPT_STAGES[stage]);
    }, 8000);
    try {
      setAdapt(
        await adaptCvAsync(jobId, {
          onPoll: (attempt, status) => {
            if (status.status === "done") {
              setAdaptStage("Listo ✓");
            } else if (attempt > 4) {
              // Tras ~12s sin done, casi seguro esta en Chromium/PDF.
              setAdaptStage(ADAPT_STAGES[2]);
            } else if (attempt > 1) {
              setAdaptStage(ADAPT_STAGES[1]);
            }
          },
        }),
      );
    } catch (e) {
      const code =
        e instanceof Error && "code" in e
          ? String((e as AdaptAsyncError).code || "UNKNOWN_ERROR")
          : "UNKNOWN_ERROR";
      if (code === "PROFILE_INCOMPLETE") {
        setProfileIncomplete({
          message: e instanceof Error ? e.message : adaptErrorMessage(code),
        });
      } else {
        setError(
          e instanceof Error ? e.message : adaptErrorMessage(code),
        );
      }
    } finally {
      window.clearInterval(timer);
      setAdapting(false);
      setAdaptStage(null);
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
        {profileIncomplete && (
          <div className="alert-warning" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, marginBottom: 16, padding: 16, borderRadius: 8, background: "var(--warning-bg)", border: "1px solid var(--warning-border)" }}>
            <div style={{ flex: 1 }}>
              <strong style={{ display: "block", marginBottom: 4 }}>Perfil incompleto</strong>
              <span style={{ fontSize: 14 }}>{profileIncomplete.message}</span>
            </div>
            <Link
              to="/profile"
              className="btn btn-primary btn-sm"
              style={{ whiteSpace: "nowrap" }}
            >
              Completar perfil
            </Link>
          </div>
        )}
        {error && <div className="alert-error">{error}</div>}
        {!jobId ? (
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
            onAdapt={runAdapt}
            adapting={adapting}
            adaptStage={adaptStage}
            adaptResult={adapt}
            onShowCv={() => void showCv()}
            generatingCv={generating}
            onGenerateCv={(force: boolean) => void generate(force)}
            cvView={cvView}
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

function AdaptResultCard({
  jobId,
  result,
}: {
  jobId: number | string;
  result: AdaptCvResult;
}) {
  const [showPreview, setShowPreview] = useState(false);
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 className="card-title">CV personalizado</h3>
      <p className="card-sub">
        {result.job.title}
        {result.job.company ? ` · ${result.job.company}` : ""}
      </p>
      <p style={{ fontSize: 26, fontWeight: 700, margin: "0 0 8px" }}>
        {result.matching.percentage}%
        <span
          style={{
            fontSize: 13,
            fontWeight: 400,
            color: "var(--text-muted)",
          }}
        >
          {" "}
          de coincidencia
        </span>
      </p>
      {result.matching.matched_skills.length > 0 && (
        <>
          <p className="card-sub">Skills coincidentes</p>
          <div className="skill-chips">
            {result.matching.matched_skills.map((s) => (
              <span key={s} className="chip">
                {s} ✓
              </span>
            ))}
          </div>
        </>
      )}
      {result.matching.missing_skills.length > 0 && (
        <>
          <p className="card-sub" style={{ marginTop: 10 }}>
            Faltantes en tu perfil
          </p>
          <div className="skill-chips">
            {result.matching.missing_skills.slice(0, 12).map((s) => (
              <span key={s} className="chip chip-missing">
                {s} ✕
              </span>
            ))}
          </div>
        </>
      )}
      {result.cv.experiences.length > 0 && (
        <p className="card-sub" style={{ marginTop: 10 }}>
          Experiencia seleccionada:{" "}
          <strong>
            {result.cv.experiences
              .map((e) => e.title || e.company)
              .filter(Boolean)
              .join(" · ")}
          </strong>
        </p>
      )}
      {result.cv.projects.length > 0 && (
        <p className="card-sub">
          Proyecto seleccionado: <strong>{result.cv.projects[0]}</strong>
        </p>
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => setShowPreview((v) => !v)}
        >
          <Eye size={14} /> {showPreview ? "Ocultar CV" : "Ver CV"}
        </button>
        <a
          className="btn btn-primary btn-sm"
          href={adaptDownloadUrl(jobId, "pdf")}
          target="_blank"
          rel="noreferrer"
        >
          <Download size={14} /> Descargar PDF
        </a>
        <a
          className="btn btn-ghost btn-sm"
          href={adaptDownloadUrl(jobId, "html")}
          target="_blank"
          rel="noreferrer"
          title="Ver HTML si PDF no está disponible"
        >
          <FileText size={14} /> HTML
        </a>
      </div>
      {showPreview && (
        <div style={{ marginTop: 10 }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
            <span className="card-sub" style={{ fontSize: 13, alignSelf: "center" }}>
              Vista previa del PDF:
            </span>
            <a
              className="btn btn-ghost btn-xs"
              href={adaptDownloadUrl(jobId, "pdf")}
              target="_blank"
              rel="noreferrer"
              title="Abrir en nueva pestaña"
            >
              <ExternalLink size={12} /> Abrir en pestaña nueva
            </a>
          </div>
          <iframe
            title="CV personalizado"
            src={adaptDownloadUrl(jobId, "pdf")}
            style={{
              width: "100%",
              height: 600,
              border: "1px solid var(--border)",
              borderRadius: 8,
              backgroundColor: "var(--bg)",
            }}
            onLoad={() => {
              // Si el iframe carga un error 404, intentar con HTML
            }}
          />
          <p className="card-sub" style={{ marginTop: 8, fontSize: 12, color: "var(--text-muted)" }}>
            Si no se ve el PDF, usa <strong>«Abrir en pestaña nueva»</strong> o el botón <strong>HTML</strong> arriba.
          </p>
        </div>
      )}
      <p className="card-sub" style={{ marginTop: 8, fontSize: 12, color: "var(--text-muted)" }}>
        Si el PDF no está disponible (Chromium no instalado en el servidor),
        usa el botón <strong>HTML</strong> para ver el curriculum en el navegador
        y guardarlo como PDF desde allí (Ctrl+P → Guardar como PDF).
      </p>
    </div>
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
  onAdapt,
  adapting,
  adaptStage,
  adaptResult,
  onShowCv,
  generatingCv,
  onGenerateCv,
  cvView,
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
  onAdapt: () => void;
  adapting: boolean;
  adaptStage: string | null;
  adaptResult: AdaptCvResult | null;
  onShowCv: () => void;
  generatingCv: boolean;
  onGenerateCv: (force: boolean) => void;
  cvView: {
    phase: "loading" | "ready" | "error";
    data?: CustomizedCv;
    error?: string;
  } | null;
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
          {job.status !== "applied" && job.status !== "discarded" && (
            <button className="btn btn-primary btn-sm" disabled={busy} onClick={onApply}>
              <Send /> Postularme
            </button>
          )}
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
          <button
            className="btn btn-ghost btn-sm"
            disabled={adapting}
            onClick={onAdapt}
            title="Adapta el perfil y genera el PDF en segundo plano (POST /jobs/{id}/adapt-cv/start + polling /status)"
          >
            <Sparkles size={15} /> {adapting ? adaptStage ?? "Adaptando…" : "Adaptar perfil"}
          </button>
          <button
            className="btn btn-ghost btn-sm"
            disabled={generatingCv}
            onClick={onShowCv}
            title="Ver el CV adaptado a esta oferta (GET /jobs/{id}/customized-cv, sin consumir IA)"
          >
            <Eye size={15} /> Ver CV adaptado
          </button>
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

      {adaptResult && (
        <AdaptResultCard jobId={job.id} result={adaptResult} />
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="card-title">
          <FileText size={15} style={{ verticalAlign: -2 }} /> CV adaptado
          a esta oferta
        </h3>
        {!cvView && (
          <p className="card-sub" style={{ marginBottom: 0 }}>
            Se genera solo bajo demanda al abrir esta oferta. Si ya existe,
            se reutiliza sin consumir IA.
          </p>
        )}
        {cvView?.phase === "loading" && (
          <p className="card-sub" style={{ marginBottom: 0 }}>
            Adaptando CV para el puesto…
          </p>
        )}
        {cvView?.phase === "error" && (
          <div>
            <p style={{ color: "var(--danger)", fontSize: 13 }}>
              No fue posible generar el CV: {cvView.error}
            </p>
            <button
              className="btn btn-ghost btn-sm"
              disabled={generatingCv}
              onClick={() => onGenerateCv(true)}
            >
              <RefreshCw size={14} /> Reintentar
            </button>
          </div>
        )}
        {cvView?.phase === "ready" && cvView.data?.state === "NOT_GENERATED" && (
          <div>
            <p className="card-sub">
              Aún no hay CV para esta oferta.{" "}
              {cvView.data.hint ?? ""}
            </p>
            <button
              className="btn btn-primary btn-sm"
              disabled={generatingCv}
              onClick={() => onGenerateCv(false)}
            >
              <FileText size={14} />{" "}
              {generatingCv ? "Generando…" : "Generar CV adaptado"}
            </button>
          </div>
        )}
        {cvView?.phase === "ready" && cvView.data?.state === "ERROR" && (
          <div>
            <p style={{ color: "var(--danger)", fontSize: 13 }}>
              No fue posible generar el CV: {cvView.data.error}
            </p>
            <button
              className="btn btn-ghost btn-sm"
              disabled={generatingCv}
              onClick={() => onGenerateCv(true)}
            >
              <RefreshCw size={14} /> Reintentar
            </button>
          </div>
        )}
        {cvView?.phase === "ready" && cvView.data?.state === "READY" && (
          <div>
            <p className="card-sub" style={{ marginTop: 0 }}>
              CV listo · versión {cvView.data.version} · generado el{" "}
              {cvView.data.created_at
                ? new Date(cvView.data.created_at).toLocaleString()
                : "—"}
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
              {cvView.data.download_pdf && (
                <a
                  className="btn btn-primary btn-sm"
                  href={`${API_URL}${cvView.data.download_pdf}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Eye size={14} /> Ver PDF
                </a>
              )}
              {cvView.data.download_tex && (
                <a
                  className="btn btn-ghost btn-sm"
                  href={`${API_URL}${cvView.data.download_tex}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Descargar LaTeX
                </a>
              )}
              {!cvView.data.download_pdf && (
                <a
                  className="btn btn-ghost btn-sm"
                  href={`${API_URL}/jobs/${cvView.data.job_id}/cv/download?format=tex`}
                  target="_blank"
                  rel="noreferrer"
                  title="Ver LaTeX en el navegador y guardar como PDF (Ctrl+P)"
                >
                  <FileText size={14} /> Ver LaTeX
                </a>
              )}
              <button
                className="btn btn-ghost btn-sm"
                disabled={generatingCv}
                onClick={() => onGenerateCv(true)}
                title="Genera una nueva versión (consume IA)"
              >
                <RefreshCw size={14} /> Regenerar
              </button>
            </div>
            {cvView.data.download_pdf ? (
              <iframe
                title={`CV adaptado v${cvView.data.version}`}
                src={`${API_URL}${cvView.data.download_pdf}`}
                style={{
                  width: "100%",
                  height: 560,
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                }}
              />
            ) : (
              <div className="card" style={{ marginTop: 10, padding: 12 }}>
                <p className="card-sub" style={{ marginBottom: 8 }}>
                  <strong>PDF no disponible</strong> (pdflatex no instalado en el servidor).
                </p>
                <p className="card-sub" style={{ marginBottom: 8, fontSize: 13 }}>
                  Opciones para obtener tu PDF:
                </p>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                  <li style={{ marginBottom: 4 }}>
                    <strong>Opción 1:</strong> Haz clic en <strong>«Ver LaTeX»</strong> arriba,
                    se abre el código LaTeX en el navegador → <kbd>Ctrl+P</kbd> → Guardar como PDF.
                  </li>
                  <li style={{ marginBottom: 4 }}>
                    <strong>Opción 2:</strong> Descarga el <strong>LaTeX</strong>,
                    compílalo localmente con <code>pdflatex cv.tex</code> (requiere TeX Live instalado).
                  </li>
                  <li style={{ marginBottom: 4 }}>
                    <strong>Opción 3:</strong> Usa <a href="https://overleaf.com" target="_blank" rel="noreferrer">Overleaf</a>
                    (gratis online): sube el .tex y compila online.
                  </li>
                  <li>
                    <strong>Opción 4 (recomendada):</strong> Usa el botón <strong>«Adaptar perfil»</strong> (✨)
                    que genera PDF via HTML+Chromium (no requiere LaTeX).
                  </li>
                </ul>
              </div>
            )}
          </div>
        )}
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