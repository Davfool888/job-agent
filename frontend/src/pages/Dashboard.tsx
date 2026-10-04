import { useEffect, useMemo, useState } from "react";
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
import { useJobs, useSources, useStats } from "../hooks/useApi";
import { useJobSearchStream } from "../hooks/useJobSearchStream";
import { useSearchSession } from "../context/SearchSessionContext";
import { discoverJobs } from "../services/jobs";
import { fetchSchedulerStatus } from "../services/searchProfiles";
import type { SchedulerStatus } from "../types/searchProfile";
import { timeAgo } from "../utils/format";
import { COLOMBIAN_CITIES } from "../utils/cities";
import { STATUS_LABELS, sourceLabel } from "../utils/constants";
import { canonicalLocation } from "../utils/profileOptions";

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
  const search = useJobSearchStream();
  const { sources } = useSources();
  // Antigüedad maxima por defecto (se guarda en este navegador).
  const [maxAge, setMaxAge] = useState<number>(() =>
    Number(window.localStorage.getItem("jobagent_default_max_age") ?? 0) || 0,
  );
  const changeMaxAge = (v: number) => {
    setMaxAge(v);
    window.localStorage.setItem("jobagent_default_max_age", String(v));
  };
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
  const [sched, setSched] = useState<SchedulerStatus | null>(null);

  useEffect(() => {
    fetchSchedulerStatus()
      .then(setSched)
      .catch(() => setSched(null));
  }, []);

  const all = useMemo(() => jobs.data ?? [], [jobs.data]);
  const byStatus = stats.data?.by_status ?? {};

  // Ciudad canonica: un typo en "Bogotà" hacia que el filtro de ubicacion
  // del scraper devuelva 0 ofertas sin explicar por que.
  const cityValue = canonicalLocation(city, COLOMBIAN_CITIES);
  const cityOptions = useMemo(
    () =>
      cityValue && !COLOMBIAN_CITIES.includes(cityValue)
        ? [...COLOMBIAN_CITIES, cityValue]
        : COLOMBIAN_CITIES,
    [cityValue],
  );

  // Actividad reciente = solo nuevas: lo visto/decidido vive en sus
  // secciones (Vistas/Postuladas/Descartadas) y no se repite aquí.
  const recentActivity = useMemo(
    () => all.filter((j) => j.status === "new").slice(0, 8),
    [all],
  );

  const runSearch = async () => {
    if (!query.trim() || search.searching) return;
    setMulti(null);
    setDiscovery(null);
    setResult(null);
    try {
      if (source === "all" && sources.length > 0) {
        // Todas las fuentes, una por una en streaming: las ofertas se
        // acumulan en vivo a medida que cada fuente las entrega.
        const summaries: SourceSummary[] = [];
        let first = true;
        for (const src of sources) {
          try {
            const last = await search.run(
              query.trim(), pages, src, city, maxAge, !first,
            );
            first = false;
            summaries.push({
              source: src,
              found: last?.found ?? 0,
              saved: last?.saved ?? 0,
            });
          } catch {
            first = false;
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
        const last = await search.run(query.trim(), pages, source, city, maxAge);
        if (last) {
          setResult({
            query: query.trim(),
            pages,
            source,
            location: city || null,
            found: last.found,
            saved: last.saved,
            jobs: [],
          });
        }
      }
      jobs.reload();
      setRefreshKey((k) => k + 1);
    } catch {
      /* el error ya queda en search.searchError */
    }
  };

  // Queries del descubrimiento: SIEMPRE parten del cargo escrito en
  // el input (mas sus palabras significativas), nunca de packs fijos.
  // Asi "abogado junior", "ingeniero civil", etc. traen sus vacantes.
  const buildDiscoveryQueries = (raw: string): string[] => {
    const base = raw.trim();
    if (!base) return [];
    const out = [base];
    for (const token of base.split(/[\s,;]+/)) {
      const t = token.trim();
      if (
        t.length > 3 &&
        !out.some((q) => q.toLowerCase() === t.toLowerCase())
      ) {
        out.push(t);
      }
    }
    return out.slice(0, 4);
  };

  const runDiscovery = async () => {
    if (discovering) return;
    setDiscoveryError(null);
    setDiscovery(null);
    const queries = buildDiscoveryQueries(query);
    if (queries.length === 0) {
      setDiscoveryError(
        "Escribe un cargo en el buscador (ej: abogado junior) para descubrir sus vacantes.",
      );
      return;
    }
    setDiscovering(true);
    try {
      // Descubrimiento por capas sobre EL CARGO del input (o
      // computrabajo si está "todas"): el texto + sus variantes.
      const src = source === "all" ? "computrabajo" : source;
      const summary = await discoverJobs({
        source: src,
        pages: 1,
        queries,
      });
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
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input
              className="input"
              style={{ width: 200 }}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ej: desarrollador python"
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
            />
            <select
              className="select"
              value={cityValue}
              onChange={(e) => setCity(e.target.value)}
              style={{ maxWidth: 165 }}
              title="Filtra por ciudad antes de guardar. Vacío = todo el país. Elegir de la lista evita búsquedas con 0 resultados por error de escritura."
            >
              <option value="">Todo el país</option>
              {cityOptions.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
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
            <select
              className="select"
              value={String(maxAge)}
              onChange={(e) => changeMaxAge(Number(e.target.value))}
              title="Antigüedad máxima por defecto: descarta ofertas con publicación más vieja antes de guardar. Se recuerda en este navegador."
            >
              <option value="0">Todas</option>
              <option value="1">Hoy</option>
              <option value="3">3 días</option>
              <option value="7">7 días</option>
              <option value="14">14 días</option>
              <option value="30">30 días</option>
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
              title="Descubrimiento por capas sobre el cargo escrito arriba (texto + variantes), con análisis de contenido (POST /jobs/discover). Encuentra ofertas cuyo título no es exacto."
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
        {(search.searching || search.jobs.length > 0) && (
          <div className="card" style={{ marginBottom: 16 }}>
            <div
              style={{
                display: "flex",
                gap: 8,
                alignItems: "center",
                marginBottom: 8,
              }}
            >
              <p style={{ margin: 0, fontSize: 13, flex: 1 }}>
                {search.analyzing ? (
                  <>
                    Analizando <strong>{search.found}</strong> ofertas…
                  </>
                ) : search.searching ? (
                  <>
                    Buscando <strong>“{query}”</strong>
                    {search.pages > 1 && (
                      <>
                        {" "}· página {Math.max(search.page, 1)}/{search.pages}
                      </>
                    )}{" "}
                    · <strong>{search.found}</strong> encontradas hasta ahora
                  </>
                ) : search.cancelled ? (
                  <>
                    Búsqueda detenida con <strong>{search.found}</strong>{" "}
                    ofertas (lo guardado persiste).{" "}
                    <Link to="/jobs">Ver ofertas</Link>
                  </>
                ) : (
                  <>
                    <strong>{search.found}</strong> ofertas encontradas.{" "}
                    <Link to="/jobs">Ver ofertas</Link>
                  </>
                )}
              </p>
              {search.searching && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={search.cancel}
                >
                  Detener
                </button>
              )}
            </div>
            {search.jobs.length > 0 && (
              <ul
                style={{
                  margin: "8px 0 0",
                  paddingLeft: 18,
                  fontSize: 13,
                  maxHeight: 300,
                  overflowY: "auto",
                }}
              >
                {search.jobs.map((j) => (
                  <li key={j.id} style={{ marginBottom: 4 }}>
                    <Link to={`/jobs/${j.id}`}>{j.title}</Link>{" "}
                    <span style={{ color: "var(--text-muted)" }}>
                      · {j.company || "Empresa no indicada"}
                      {j.location ? ` · ${j.location}` : ""} ·{" "}
                      {sourceLabel(j.source)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
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
            {discovery.per_query.length > 0 && (
              <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12 }}>
                {discovery.per_query.map((q) => (
                  <li key={q.query}>
                    <strong>“{q.query}”</strong>: {q.found} encontradas,{" "}
                    {q.saved} guardadas
                  </li>
                ))}
              </ul>
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
              {result.max_age_days ? (
                <> · últimos {result.max_age_days} días</>
              ) : null}
              : {result.found} encontradas
              {result.filtered_out ? (
                <> ({result.filtered_out} viejas filtradas)</>
              ) : null}
              , {result.saved} guardadas/actualizadas (sin duplicar links).{" "}
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
                {sched && !sched.enabled && (
                  <div className="notice-pending">
                    <Target size={15} />
                    <span>
                      Scheduler inactivo en el backend
                      (SCHEDULER_ENABLED=false o instancia dormida en plan
                      gratuito). Configura los perfiles en{" "}
                      <Link to="/search">Búsqueda</Link> y un cron externo
                      hacia <code>POST /scheduler/tick</code>.
                    </span>
                  </div>
                )}
                <dl className="kv">
                  <dt>Agente</dt>
                  <dd>
                    {sched
                      ? sched.enabled
                        ? "● Activo"
                        : "○ Inactivo"
                      : "…"}
                  </dd>
                  <dt>Ofertas en BD</dt>
                  <dd>{stats.data?.total ?? 0}</dd>
                  <dt>Ofertas analizadas</dt>
                  <dd>{stats.data?.scored_count ?? 0}</dd>
                  <dt>Último tick</dt>
                  <dd>
                    {sched?.last_tick.at
                      ? `${timeAgo(sched.last_tick.at)} (${sched.last_tick.profiles} perfiles, ${sched.last_tick.new} nuevas)`
                      : "Sin ticks registrados"}
                  </dd>
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
