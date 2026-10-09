import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  Archive,
  BookmarkCheck,
  Briefcase,
  Building2,
  Clock,
  Inbox,
  RefreshCw,
  Search,
  Send,
  Target,
  X,
} from "lucide-react";
import { Header } from "../components/layout/Header";
import { ErrorState, LoadingState } from "../components/jobs/States";
import { useJobs, useSources, useStats } from "../hooks/useApi";
import { useJobSearchStream } from "../hooks/useJobSearchStream";
import { useSearchSession } from "../context/SearchSessionContext";
import { fetchSchedulerStatus } from "../services/searchProfiles";
import type { SchedulerStatus } from "../types/searchProfile";
import { timeAgo } from "../utils/format";
import { rankJobs, splitKeywords } from "../utils/searchRank";
import { COLOMBIAN_CITIES } from "../utils/cities";
import { STATUS_LABELS, sourceLabel } from "../utils/constants";
import { canonicalLocation } from "../utils/profileOptions";
import { useAuth } from "../context/AuthContext";

interface SourceSummary {
  source: string;
  found: number;
  saved: number;
  error?: string;
}

interface SearchHistoryItem {
  query: string;
  keywords: string;
  city: string;
  source: string;
  pages: number;
  maxAge: number;
  timestamp: number;
}

const MAX_HISTORY_ITEMS = 4;
const STORAGE_KEY_PREFIX = "jobagent_search_history_";

export function Dashboard() {
  const { firebaseUser } = useAuth();
  const userId = firebaseUser?.uid ?? "guest";

  const [refreshKey, setRefreshKey] = useState(0);
  const jobs = useJobs();
  const stats = useStats(refreshKey);
  const search = useJobSearchStream();
  const { sources } = useSources();
  // Antigüedad maxima por defecto (se guarda en este navegador).
  const [maxAge, setMaxAge] = useState<number>(() =>
    Number(window.localStorage.getItem("jobagent_default_max_age") ?? 0) || 0,
  );
  const changeMaxAge = useCallback((v: number) => {
    setMaxAge(v);
    window.localStorage.setItem("jobagent_default_max_age", String(v));
  }, []);
  // Sesion de busqueda compartida: persiste al navegar entre secciones,
  // no re-ejecuta scraping al volver y no resetea la consulta.
  const {
    query,
    keywords,
    source,
    pages,
    city,
    setQuery,
    setKeywords,
    setSource,
    setPages,
    setCity,
    result,
    setResult,
    multi,
    setMulti,
  } = useSearchSession();
  const [sched, setSched] = useState<SchedulerStatus | null>(null);
  // Generación de búsqueda: si el usuario sigue escribiendo, la
  // anterior se abandona y solo la última pinta resultados.
  const runIdRef = useRef(0);
  // Historial de búsquedas (últimas 4 por usuario)
  const [searchHistory, setSearchHistory] = useState<SearchHistoryItem[]>(() => {
    try {
      const raw = window.localStorage.getItem(`${STORAGE_KEY_PREFIX}${userId}`);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) return parsed.slice(0, MAX_HISTORY_ITEMS);
      }
    } catch {
      /* ignore */
    }
    return [];
  });
  const [showHistory, setShowHistory] = useState(false);
  // Búsqueda progresiva: estado para controlar fases
  const [progressivePhase, setProgressivePhase] = useState<"idle" | "main" | "variations">("idle");
  const [variationQueries, setVariationQueries] = useState<string[]>([]);
  const [currentVariationIndex, setCurrentVariationIndex] = useState(0);
  const variationQueriesRef = useRef<string[]>([]);
  const currentVariationIndexRef = useRef(0);

  useEffect(() => {
    fetchSchedulerStatus()
      .then(setSched)
      .catch(() => setSched(null));
  }, []);

  // Cargar historial cuando cambia el usuario - se usa el estado inicial
  // del useState y se actualiza solo si userId cambia realmente
  const prevUserIdRef = useRef(userId);
  useEffect(() => {
    if (prevUserIdRef.current === userId) return;
    prevUserIdRef.current = userId;
    try {
      const raw = window.localStorage.getItem(`${STORAGE_KEY_PREFIX}${userId}`);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          setSearchHistory(parsed.slice(0, MAX_HISTORY_ITEMS)); // eslint-disable-line react-hooks/set-state-in-effect
        } else {
          setSearchHistory([]); // eslint-disable-line react-hooks/set-state-in-effect
        }
      } else {
        setSearchHistory([]); // eslint-disable-line react-hooks/set-state-in-effect
      }
    } catch {
      setSearchHistory([]); // eslint-disable-line react-hooks/set-state-in-effect
    }
  }, [userId]);

  const saveToHistory = useCallback((item: Omit<SearchHistoryItem, "timestamp">) => {
    const itemWithTimestamp: SearchHistoryItem = { ...item, timestamp: Date.now() };
    setSearchHistory((prev) => {
      const filtered = prev.filter(
        (h) => !(h.query === itemWithTimestamp.query && h.city === itemWithTimestamp.city && h.source === itemWithTimestamp.source)
      );
      const updated = [itemWithTimestamp, ...filtered].slice(0, MAX_HISTORY_ITEMS);
      try {
        window.localStorage.setItem(`${STORAGE_KEY_PREFIX}${userId}`, JSON.stringify(updated));
      } catch {
        /* ignore */
      }
      return updated;
    });
  }, [userId]);

  const selectHistoryItem = useCallback((item: SearchHistoryItem) => {
    setQuery(item.query);
    setKeywords(item.keywords);
    setCity(item.city);
    setSource(item.source);
    setPages(item.pages);
    changeMaxAge(item.maxAge);
    setShowHistory(false);
  }, [setQuery, setKeywords, setCity, setSource, setPages, changeMaxAge]);

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

  // Ranking en vivo: el cargo manda, las palabras clave acercan
  // puestos relacionados. Agrupa en exactas / similares / resto.
  const ranked = useMemo(
    () => rankJobs(search.jobs, query, splitKeywords(keywords).join(" ")),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [search.jobs, query, keywords],
  );
  const exactHits = useMemo(
    () => ranked.filter((r) => r.tier === "exact"),
    [ranked],
  );
  const relatedHits = useMemo(
    () => ranked.filter((r) => r.tier === "related"),
    [ranked],
  );
  const otherHits = useMemo(
    () => ranked.filter((r) => r.tier === "other"),
    [ranked],
  );

  // Actividad reciente = solo nuevas: lo visto/decidido vive en sus
  // secciones (Vistas/Postuladas/Descartadas) y no se repite aquí.
  const recentActivity = useMemo(
    () => all.filter((j) => j.status === "new").slice(0, 8),
    [all],
  );

  // Construir queries de variación para búsqueda progresiva
  const buildVariationQueries = useCallback((baseQuery: string, baseKeywords: string): string[] => {
    const queries: string[] = [];
    const seen = new Set<string>();
    const add = (q: string) => {
      const t = q.trim().toLowerCase();
      if (t && t.length >= 2 && !seen.has(t)) {
        seen.add(t);
        queries.push(q.trim());
      }
    };

    // 1. Query principal (ya se buscó en fase main)
    // 2. Palabras clave individuales
    for (const kw of splitKeywords(baseKeywords)) add(kw);
    // 3. Tokens del query principal (palabras > 3 chars)
    for (const token of baseQuery.split(/[\s,;]+/)) {
      if (token.trim().length > 3) add(token);
    }
    // 4. Combinaciones query + keyword
    const mainTokens = baseQuery.split(/[\s,;]+/).filter((t) => t.trim().length > 3);
    for (const kw of splitKeywords(baseKeywords)) {
      for (const token of mainTokens) {
        add(`${token} ${kw}`);
      }
    }
    // Limitar a 6 variaciones para no saturar
    return queries.slice(0, 6);
  }, []);

  const runSearch = async (runId?: number) => {
    const myRun = runId ?? ++runIdRef.current;
    if (!query.trim()) return;
    // Si hay una búsqueda en curso de otra generación, se cancela.
    search.cancel();
    setMulti(null);
    setResult(null);
    // Si "todas" aún no cargó (clic manual rapidísimo), se usa
    // computrabajo para no pedirle "all" al backend (400).
    const effectiveSource = source === "all" && sources.length === 0 ? "computrabajo" : source;

    // Guardar en historial (timestamp se añade en saveToHistory)
    saveToHistory({
      query: query.trim(),
      keywords,
      city,
      source: effectiveSource,
      pages,
      maxAge,
    });
    setShowHistory(false);

    // FASE 1: Búsqueda principal (query exacta)
    setProgressivePhase("main");
    const vQueries = buildVariationQueries(query.trim(), keywords);
    variationQueriesRef.current = vQueries;
    setVariationQueries(vQueries);
    currentVariationIndexRef.current = 0;
    setCurrentVariationIndex(0);

    try {
      if (effectiveSource === "all" && sources.length > 0) {
        // Todas las fuentes, una por una en streaming
        const summaries: SourceSummary[] = [];
        let first = true;
        for (const src of sources) {
          if (runIdRef.current !== myRun) return;
          try {
            const last = await search.run(
              query.trim(), pages, src, city, maxAge, !first,
            );
            if (runIdRef.current !== myRun) return;
            first = false;
            summaries.push({
              source: src,
              found: last?.found ?? 0,
              saved: last?.saved ?? 0,
            });
          } catch {
            if (runIdRef.current !== myRun) return;
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
        const last = await search.run(
          query.trim(), pages, effectiveSource, city, maxAge,
        );
        if (runIdRef.current !== myRun) return;
        if (last) {
          setResult({
            query: query.trim(),
            pages,
            source: effectiveSource,
            location: city || null,
            found: last.found,
            saved: last.saved,
            jobs: [],
          });
        }
      }
      jobs.reload();
      setRefreshKey((k) => k + 1);

      // FASE 2: Búsqueda de variaciones (progresiva)
      if (variationQueriesRef.current.length > 0) {
        setProgressivePhase("variations");
        await runVariations(myRun, effectiveSource);
      } else {
        setProgressivePhase("idle");
      }
    } catch {
      /* el error ya queda en search.searchError */
      setProgressivePhase("idle");
    }
  };

  const runVariations = async (myRun: number, effectiveSource: string) => {
    const variations = variationQueriesRef.current;
    let idx = currentVariationIndexRef.current;

    while (idx < variations.length && runIdRef.current === myRun) {
      const variationQuery = variations[idx];
      currentVariationIndexRef.current = idx;
      setCurrentVariationIndex(idx);

      try {
        if (effectiveSource === "all" && sources.length > 0) {
          for (const src of sources) {
            if (runIdRef.current !== myRun) return;
            await search.run(variationQuery, pages, src, city, maxAge, true);
          }
        } else {
          await search.run(variationQuery, pages, effectiveSource, city, maxAge, true);
        }
        jobs.reload();
        setRefreshKey((k) => k + 1);
        // Pequeña pausa entre variaciones para no saturar
        await new Promise((r) => setTimeout(r, 500));
      } catch {
        // Continuar con la siguiente variación aunque falle una
      }
      idx++;
      currentVariationIndexRef.current = idx;
      setCurrentVariationIndex(idx);
    }
    setProgressivePhase("idle");
  };

  // Cancelar búsqueda progresiva completa
  const cancelAll = () => {
    search.cancel();
    runIdRef.current++; // Invalida cualquier fase en curso
    setProgressivePhase("idle");
  };

  return (
    <>
      <Header
        title="Dashboard"
        subtitle="Resumen del estado de tu búsqueda laboral"
        actions={
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <div style={{ position: "relative", flex: 1, minWidth: 280 }}>
              <input
                className="input"
                style={{ width: "100%", paddingRight: 40 }}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setShowHistory(true);
                }}
                onFocus={() => query.trim() && setShowHistory(true)}
                placeholder="Ej: abogado junior, enfermera, contador…"
                title="Cargo o puesto a buscar. Presiona Enter o click en 'Buscar nuevas ofertas'."
                onKeyDown={(e) => e.key === "Enter" && void runSearch()}
              />
              {showHistory && searchHistory.length > 0 && (
                <div
                  style={{
                    position: "absolute",
                    top: "100%",
                    left: 0,
                    right: 0,
                    marginTop: 4,
                    background: "var(--card-bg)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
                    zIndex: 100,
                    maxHeight: 200,
                    overflowY: "auto",
                  }}
                >
                  <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--text-muted)", borderBottom: "1px solid var(--border)" }}>
                    Últimas búsquedas
                  </div>
                  {searchHistory.map((item, idx) => (
                    <button
                      key={idx}
                      style={{
                        width: "100%",
                        textAlign: "left",
                        padding: "10px 12px",
                        background: "transparent",
                        border: "none",
                        cursor: "pointer",
                        fontSize: 13,
                        color: "var(--text)",
                        display: "flex",
                        flexDirection: "column",
                        gap: 2,
                      }}
                      onClick={() => selectHistoryItem(item)}
                      onMouseOver={() => {}}
                    >
                      <span style={{ fontWeight: 500 }}>{item.query}</span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {item.city ? `${item.city} · ` : ""}
                        {sourceLabel(item.source)}
                        {item.keywords ? ` · ${item.keywords}` : ""}
                        {item.pages > 1 ? ` · ${item.pages} págs` : ""}
                        {item.maxAge > 0 ? ` · últimos ${item.maxAge}d` : ""}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  pointerEvents: "none",
                }}
                onClick={() => setShowHistory(false)}
              />
            </div>
            <input
              className="input"
              style={{ width: 190 }}
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="Palabras clave: MIP, riego, QGIS…"
              title="Secundarias: separadas por coma. Acercan puestos relacionados con esas palabras en los resultados."
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
              onClick={() => void runSearch()}
              title="Busca ofertas con el cargo escrito; luego explora variaciones automáticamente"
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
            {(search.searching || progressivePhase !== "idle") && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={cancelAll}
                title="Cancela la búsqueda actual y las variaciones pendientes"
              >
                <X size={14} /> Cancelar
              </button>
            )}
          </div>
        }
      />
      <div className="content">
        {search.searchError && (
          <div className="alert-error">{search.searchError}</div>
        )}
        {(search.searching || search.jobs.length > 0 || progressivePhase !== "idle") && (
          <div className="card" style={{ marginBottom: 16 }}>
            <div
              style={{
                display: "flex",
                gap: 8,
                alignItems: "center",
                marginBottom: 8,
                flexWrap: "wrap",
              }}
            >
              <p style={{ margin: 0, fontSize: 13, flex: 1, minWidth: 280 }}>
                {progressivePhase === "main" && search.searching ? (
                  <>
                    Buscando principal <strong>“{query}”</strong>
                    {search.pages > 1 && (
                      <>
                        {" "}· página {Math.max(search.page, 1)}/{search.pages}
                      </>
                    )}{" "}
                    · <strong>{search.found}</strong> encontradas
                  </>
                ) : progressivePhase === "variations" ? (
                  <>
                    <Clock size={14} style={{ verticalAlign: "middle", marginRight: 4 }} />
                    Explorando variaciones ({currentVariationIndex}/{variationQueries.length})
                    · <strong>{search.found}</strong> ofertas totales
                    {variationQueries[currentVariationIndex] && (
                      <>
                        {" "}· actual: <em>"{variationQueries[currentVariationIndex]}"</em>
                      </>
                    )}
                  </>
                ) : search.analyzing ? (
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
              {(search.searching || progressivePhase !== "idle") && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={cancelAll}
                >
                  <X size={14} /> Cancelar todo
                </button>
              )}
            </div>
            {search.jobs.length > 0 && (
              <>
                {exactHits.length > 0 && (
                  <>
                    <p style={{ margin: "8px 0 4px", fontSize: 13 }}>
                      🎯 <strong>{exactHits.length}</strong> buscan ese rol
                    </p>
                    <ul
                      style={{
                        margin: "0 0 4px",
                        paddingLeft: 18,
                        fontSize: 13,
                        maxHeight: 220,
                        overflowY: "auto",
                      }}
                    >
                      {exactHits.map(({ job, hits }) => (
                        <li key={job.id} style={{ marginBottom: 4 }}>
                          <Link to={`/jobs/${job.id}`}>{job.title}</Link>{" "}
                          <span style={{ color: "var(--text-muted)" }}>
                            · {job.company || "Empresa no indicada"}
                            {job.location ? ` · ${job.location}` : ""} ·{" "}
                            {sourceLabel(job.source)}
                            {hits.length > 0 && ` · ✓ ${hits.join(", ")}`}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {relatedHits.length > 0 && (
                  <>
                    <p style={{ margin: "8px 0 4px", fontSize: 13 }}>
                      🔎 <strong>{relatedHits.length}</strong> roles similares
                    </p>
                    <ul
                      style={{
                        margin: "0 0 4px",
                        paddingLeft: 18,
                        fontSize: 13,
                        maxHeight: 220,
                        overflowY: "auto",
                      }}
                    >
                      {relatedHits.map(({ job, hits }) => (
                        <li key={job.id} style={{ marginBottom: 4 }}>
                          <Link to={`/jobs/${job.id}`}>{job.title}</Link>{" "}
                          <span style={{ color: "var(--text-muted)" }}>
                            · {job.company || "Empresa no indicada"}
                            {job.location ? ` · ${job.location}` : ""} ·{" "}
                            {sourceLabel(job.source)}
                            {hits.length > 0 && ` · ~ ${hits.join(", ")}`}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {otherHits.length > 0 && (
                  <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--text-muted)" }}>
                    +{otherHits.length} sin coincidencia directa
                    (afina con palabras clave).
                  </p>
                )}
              </>
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
              {result.fit_filtered &&
              Object.values(result.fit_filtered).reduce((a, b) => a + b, 0) > 0 ? (
                <>
                  {" "}({Object.values(result.fit_filtered).reduce((a, b) => a + b, 0)}{" "}
                  fuera de tu rango)
                </>
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
