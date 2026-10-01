import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Archive,
  BookmarkCheck,
  Briefcase,
  Building2,
  Inbox,
  Layers,
  RefreshCw,
  Search,
  Send,
  Target,
} from "lucide-react";
import { Header } from "../components/layout/Header";
import { ErrorState, LoadingState } from "../components/jobs/States";
import { useJobs, useJobSearch, useSources, useStats } from "../hooks/useApi";
import { useSearchSession } from "../context/SearchSessionContext";
import { discoverJobs } from "../services/jobs";
import { timeAgo } from "../utils/format";
import { COLOMBIAN_CITIES } from "../utils/cities";
import { STATUS_LABELS, sourceLabel } from "../utils/constants";

interface SourceSummary {
  source: string;
  found: number;
  saved: number;
  error?: string;
}

export function Dashboard() {
  const [refreshKey, setRefreshKey] = useState(0);
  const jobs = useJobs();
  const stats = useStats(refreshKey);
  const search = useJobSearch();
  const { sources } = useSources();
  // Sesion de busqueda compartida: persiste al navegar entre secciones,
  // no re-ejecuta scraping al volver y no resetea la consulta.
  const {
    query,
    source,
    pages,
    city,
    setQuery,
    setSource,
    setPages,
    setCity,
    result,
    setResult,
    multi,
    setMulti,
    discovery,
    setDiscovery,
  } = useSearchSession();
  const [discovering, setDiscovering] = useState(false);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);

  const all = useMemo(() => jobs.data ?? [], [jobs.data]);
  const byStatus = stats.data?.by_status ?? {};

  const recentActivity = useMemo(() => all.slice(0, 8), [all]);

  const runSearch = async () => {
    if (!query.trim() || search.searching) return;
    setMulti(null);
    setDiscovery(null);
    setResult(null);
    try {
      if (source === "all" && sources.length > 0) {
        // Todas las fuentes, una por una (cada scraper tarda segundos).
        const summaries: SourceSummary[] = [];
        for (const src of sources) {
          try {
            const r = await search.run(query.trim(), pages, false, src, city);
            summaries.push({ source: src, found: r.found, saved: r.saved });
          } catch {
            summaries.push({
              source: src,
              found: 0,
              saved: 0,
              error: "falló (ver detalle del error arriba)",
            });
          }
        }
        setMulti(summaries);
      } else {
        const r = await search.run(query.trim(), pages, false, source, city);
        setResult(r);
      }
      jobs.reload();
      setRefreshKey((k) => k + 1);
    } catch {
      /* el error ya queda en search.searchError */
    }
  };

  const runDiscovery = async () => {
    if (discovering) return;
    setDiscoveryError(null);
    setDiscovery(null);
    setDiscovering(true);
    try {
      // Descubrimiento por capas en la fuente elegida (o computrabajo
      // si está "todas"): titulos + habilidades + responsabilidades.
      const src = source === "all" ? "computrabajo" : source;
      const summary = await discoverJobs({ source: src, pages: 1 });
      setDiscovery(summary);
      jobs.reload();
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setDiscoveryError(
        e instanceof Error ? e.message : "Error en descubrimiento",
      );
    } finally {
      setDiscovering(false);
    }
  };

  return (
    <>
      <Header
        title="Dashboard"
        subtitle="Resumen del estado de tu búsqueda laboral"
        actions={
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              className="input"
              style={{ width: 200 }}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ej: desarrollador python"
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
            />
            <input
              className="input"
              style={{ width: 150 }}
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="Ciudad (ej: Bogotá)"
              title="Filtra por ciudad antes de guardar. Vacío = todo el país."
              list="colombian-cities"
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
            />
            <datalist id="colombian-cities">
              {COLOMBIAN_CITIES.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            <select
              className="select"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              title="Fuente de empleo (GET /sources del backend)"
            >
              <option value="all">Todas las fuentes</option>
              {sources.map((s) => (
                <option key={s} value={s}>
                  {sourceLabel(s)}
                </option>
              ))}
            </select>
            <select
              className="select"
              value={String(pages)}
              onChange={(e) => setPages(Number(e.target.value))}
              title="Páginas a traer por fuente (hasta ~100 ofertas en total)"
            >
              <option value="1">1 pág. (~20)</option>
              <option value="2">2 págs. (~40)</option>
              <option value="3">3 págs. (~60)</option>
              <option value="5">5 págs. (~100)</option>
            </select>
            <button
              className="btn btn-primary btn-sm"
              disabled={search.searching}
              onClick={runSearch}
              title="Llama a GET /jobs/search del backend"
            >
              {search.searching ? (
                <>
                  <RefreshCw size={14} /> Buscando…
                </>
              ) : (
                <>
                  <Search size={14} /> Buscar nuevas ofertas
                </>
              )}
            </button>
            <button
              className="btn btn-ghost btn-sm"
              disabled={search.searching || discovering}
              onClick={runDiscovery}
              title="Descubrimiento por capas: títulos + habilidades + responsabilidades, con análisis de contenido (POST /jobs/discover). Encuentra ofertas cuyo título no es de datos."
            >
              {discovering ? (
                <>
                  <RefreshCw size={14} /> Descubriendo…
                </>
              ) : (
                <>
                  <Layers size={14} /> Descubrimiento por capas
                </>
              )}
            </button>
          </div>
        }
      />
      <div className="content">
        {search.searchError && (
          <div className="alert-error">{search.searchError}</div>
        )}
        {discoveryError && (
          <div className="alert-error">{discoveryError}</div>
        )}
        {discovery && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: "0 0 6px", fontSize: 13 }}>
              Descubrimiento por capas en{" "}
              <strong>{sourceLabel(discovery.source)}</strong>:{" "}
              {discovery.queries_run} queries, {discovery.found}{" "}
              encontradas, {discovery.saved_unique} únicas guardadas,{" "}
              {discovery.analyzed} analizadas,{" "}
              <strong>{discovery.relevant} relevantes</strong>.{" "}
              <Link to="/jobs">Ver ofertas</Link>
            </p>
            {discovery.errors.length > 0 && (
              <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>
                {discovery.errors.length} queries fallaron
                (plataforma bloqueó o sin resultados).
              </p>
            )}
          </div>
        )}
        {result && !multi && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>
              Búsqueda <strong>“{result.query}”</strong> en{" "}
              <strong>{sourceLabel(result.source)}</strong>
              {result.location ? (
                <>
                  {" "}· <strong>{result.location}</strong>
                </>
              ) : null}
              : {result.found} encontradas, {result.saved}{" "}
              guardadas/actualizadas.{" "}
              <Link to="/jobs">Ver ofertas</Link>
            </p>
          </div>
        )}
        {multi && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: "0 0 8px", fontSize: 13 }}>
              Búsqueda <strong>“{query}”</strong> en todas las fuentes.{" "}
              <Link to="/jobs">Ver ofertas</Link>
            </p>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
              {multi.map((m) => (
                <li key={m.source}>
                  <strong>{sourceLabel(m.source)}</strong>:{" "}
                  {m.error ? (
                    <span style={{ color: "var(--danger)" }}>
                      bloqueada por la plataforma ({m.error})
                    </span>
                  ) : (
                    <>
                      {m.found} encontradas, {m.saved} guardadas
                    </>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {stats.loading || jobs.loading ? (
          <LoadingState label="Cargando resumen…" />
        ) : stats.error || jobs.error ? (
          <ErrorState
            message={stats.error ?? jobs.error ?? "Error"}
            onRetry={() => {
              stats.reload();
              jobs.reload();
            }}
          />
        ) : (
          <>
            <div className="grid-stats">
              <StatCard
                icon={<Inbox size={15} />}
                label="Ofertas nuevas"
                value={byStatus.new ?? 0}
              />
              <StatCard
                icon={<BookmarkCheck size={15} />}
                label="Conservadas"
                value={byStatus.kept ?? 0}
              />
              <StatCard
                icon={<Archive size={15} />}
                label="Descartadas"
                value={byStatus.discarded ?? 0}
              />
              <StatCard
                icon={<Send size={15} />}
                label="Postuladas"
                value={byStatus.applied ?? 0}
              />
              <StatCard
                icon={<Target size={15} />}
                label="Coincidencia promedio"
                value={
                  stats.data?.avg_match !== null &&
                  stats.data?.avg_match !== undefined
                    ? `${stats.data.avg_match}%`
                    : "—"
                }
                hint={
                  stats.data?.scored_count
                    ? `sobre ${stats.data.scored_count} analizadas`
                    : "pendiente del agente"
                }
              />
              <StatCard
                icon={<Building2 size={15} />}
                label="Empresas"
                value={stats.data?.top_companies.length ?? 0}
                hint="en el top 10"
              />
              <StatCard
                icon={<Briefcase size={15} />}
                label="Total ofertas"
                value={stats.data?.total ?? 0}
              />
              <StatCard
                icon={<Search size={15} />}
                label="Búsquedas distintas"
                value={stats.data?.top_queries.length ?? 0}
              />
            </div>

            <div className="grid-2">
              <div className="card">
                <h3 className="card-title">Actividad reciente</h3>
                <p className="card-sub">
                  Últimas ofertas encontradas y su estado actual
                </p>
                {recentActivity.length === 0 ? (
                  <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                    Aún no hay ofertas. Usa “Buscar nuevas ofertas”.
                  </p>
                ) : (
                  <div className="activity-list">
                    {recentActivity.map((j) => (
                      <div key={j.id} className="activity-item">
                        <span className="activity-dot" />
                        <div>
                          <Link to={`/jobs/${j.id}`}>{j.title}</Link>
                          <div style={{ color: "var(--text-muted)" }}>
                            {j.company ?? "Empresa no indicada"} →{" "}
                            {STATUS_LABELS[j.status]}
                            {j.status === "discarded" && j.discard_reason
                              ? ` (${j.discard_reason})`
                              : ""}
                          </div>
                          <small>{timeAgo(j.created_at)}</small>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="card">
                <h3 className="card-title">Estado del agente</h3>
                <p className="card-sub">
                  Búsqueda automática y análisis IA
                </p>
                <div className="notice-pending">
                  <Target size={15} />
                  <span>
                    Funcionalidad pendiente de conexión con backend: aún no
                    existe endpoint de estado del agente, planificación de
                    búsquedas ni análisis automático de coincidencia
                    (ver <code>backend/app/agents/job_analyzer.py</code>,
                    actualmente stub). Las ofertas y decisiones de esta
                    página sí son datos reales.
                  </span>
                </div>
                <dl className="kv">
                  <dt>Agente</dt>
                  <dd>○ No configurado</dd>
                  <dt>Ofertas en BD</dt>
                  <dd>{stats.data?.total ?? 0}</dd>
                  <dt>Ofertas analizadas</dt>
                  <dd>{stats.data?.scored_count ?? 0}</dd>
                  <dt>Última oferta</dt>
                  <dd>
                    {stats.data?.last_job
                      ? `${stats.data.last_job.title} (${timeAgo(stats.data.last_job.created_at)})`
                      : "—"}
                  </dd>
                </dl>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}

function StatCard({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        {icon} {label}
      </div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}
