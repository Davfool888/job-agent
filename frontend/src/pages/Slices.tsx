import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Send,
  Undo2,
  X,
} from "lucide-react";
import { Header } from "../components/layout/Header";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { SliceCard, type SliceExit } from "../components/slices/SliceCard";
import { useJobs } from "../hooks/useApi";
import { fetchJobAnalysis, updateJobStatus } from "../services/jobs";
import { DISCARD_REASONS } from "../utils/constants";
import { uniqueLocations } from "../utils/jobs";
import { canonicalLocation, normText } from "../utils/profileOptions";
import type { Job, JobAnalysis, JobStatus } from "../types/job";
import type { StatusUpdatePayload } from "../types/job";

interface HistoryEntry {
  id: string;
  prev: JobStatus;
  dir: Exclude<SliceExit, null>;
}

interface FailedAction {
  id: string;
  payload: StatusUpdatePayload;
  label: string;
}

const SWIPE_X = 100;
const SWIPE_UP_Y = -80;
// Flick corto hacia abajo expande: 45px basta en táctil/mouse.
const EXPAND_Y = 45;
// La animación de salida dura 0.22s; a los 180ms la siguiente ya manda.
const EXIT_MS = 180;
// Tiempo mirando una tarjeta antes de registrarla como vista.
const VIEW_DELAY_MS = 800;
// Recargas de sincronización diferidas para no frenar el swipe.
const RELOAD_DEBOUNCE_MS = 6000;
// Cuántas tarjetas siguientes se montan + pre-analizan por adelantado.
const PRELOAD_AHEAD = 3;

type SortMode = "match" | "found_desc" | "found_asc";

function foundTime(j: Job): number {
  const t = new Date(j.found_at ?? j.created_at).getTime();
  return Number.isNaN(t) ? 0 : t;
}

export function Slices() {
  // Sin reload por acción: el deck avanza optimista y la red va por detrás.
  const { data, loading, error, reload } = useJobs();
  const [index, setIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [drag, setDrag] = useState({ x: 0, y: 0, dragging: false });
  const [exit, setExit] = useState<SliceExit>(null);
  const [undoBusy, setUndoBusy] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [failed, setFailed] = useState<FailedAction[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  // Decididas en la sesión: salen del deck al instante, sin esperar red.
  const [acted, setActed] = useState<Set<string>>(new Set());
  // Marcadas como vistas en la sesión: siguen en el deck con badge Abierta.
  const [viewed, setViewed] = useState<Set<string>>(new Set());
  const [kept, setKept] = useState(0);
  const [dropped, setDropped] = useState(0);
  const [applied, setApplied] = useState(0);
  // Filtros de triage.
  const [minMatch, setMinMatch] = useState(0);
  const [onlyScored, setOnlyScored] = useState(false);
  const [sort, setSort] = useState<SortMode>("found_desc");
  const [city, setCity] = useState("");
  const [discardReason, setDiscardReason] = useState<string>(DISCARD_REASONS[0]);
  const [analyses, setAnalyses] = useState<Record<string, JobAnalysis>>({});
  const [analysisLoading, setAnalysisLoading] = useState<string | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const exitTimer = useRef<number | null>(null);
  const viewTimer = useRef<number | null>(null);
  const reloadTimer = useRef<number | null>(null);
  const analysisFlight = useRef<Set<string>>(new Set());
  const emptiedRef = useRef(false);

  // Solo ofertas traídas por perfiles de búsqueda automática.
  const autoJobs = useMemo(
    () =>
      (data ?? []).filter(
        (j) =>
          ((j.status === "new" || j.status === "kept") ||
            viewed.has(String(j.id))) &&
          (j.search_profile_ids ?? []).length > 0,
      ),
    [data, viewed],
  );
  const cities = useMemo(() => uniqueLocations(autoJobs), [autoJobs]);

  const deck = useMemo(() => {
    const filtered = autoJobs.filter((j) => {
      if (acted.has(String(j.id))) return false;
      if (onlyScored && j.match_score === null) return false;
      if (minMatch > 0 && (j.match_score === null || j.match_score < minMatch))
        return false;
      if (city) {
        const jobCity = normText(canonicalLocation(j.location));
        if (jobCity !== normText(city)) return false;
      }
      return true;
    });
    return [...filtered].sort((a, b) =>
      sort === "match"
        ? (b.match_score ?? -1) - (a.match_score ?? -1) || foundTime(b) - foundTime(a)
        : sort === "found_asc"
          ? foundTime(a) - foundTime(b)
          : foundTime(b) - foundTime(a),
    );
  }, [autoJobs, acted, city, minMatch, onlyScored, sort]);
  // Sin decidir quedan fuera de filtros: ¿se acabó por decidir o por filtrar?
  const unactedCount = useMemo(
    () => autoJobs.filter((j) => !acted.has(String(j.id))).length,
    [autoJobs, acted],
  );
  const safeIndex = deck.length === 0 ? 0 : Math.min(index, deck.length - 1);
  const current: Job | undefined = deck[safeIndex];
  const upcoming: Job[] = deck.slice(safeIndex + 1, safeIndex + 1 + PRELOAD_AHEAD);
  const remaining = deck.length === 0 ? 0 : deck.length - safeIndex - 1;
  // Badge Abierta inmediato aunque el reload aún no llegue.
  const displayJob: Job | undefined =
    current && current.status === "new" && viewed.has(String(current.id))
      ? { ...current, status: "opened" as const }
      : current;

  // Reset de posición al cambiar filtros (las decisiones usan `acted`,
  // no dependen del reload).
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => {
    setIndex(0);
    setExpanded(false);
    setDrag({ x: 0, y: 0, dragging: false });
    setExit(null);
  }, [minMatch, onlyScored, sort, city]);

  useEffect(
    () => () => {
      if (exitTimer.current) window.clearTimeout(exitTimer.current);
      if (viewTimer.current) window.clearTimeout(viewTimer.current);
      if (reloadTimer.current) window.clearTimeout(reloadTimer.current);
    },
    [],
  );

  const scheduleReload = useCallback(() => {
    if (reloadTimer.current) window.clearTimeout(reloadTimer.current);
    reloadTimer.current = window.setTimeout(reload, RELOAD_DEBOUNCE_MS);
  }, [reload]);

  // Guardado en segundo plano: nunca bloquea la tarjeta siguiente.
  const saveInBackground = useCallback(
    (id: string, payload: StatusUpdatePayload, label: string) => {
      updateJobStatus(id, payload).then(
        () => scheduleReload(),
        () => {
          setFailed((f) =>
            f.some((x) => x.id === id)
              ? f
              : [...f, { id, payload, label }],
          );
        },
      );
    },
    [scheduleReload],
  );

  const retryFailed = useCallback(async () => {
    if (failed.length === 0 || retrying) return;
    setRetrying(true);
    try {
      await Promise.all(
        failed.map((f) =>
          updateJobStatus(f.id, f.payload).then(
            () => ({ id: f.id, ok: true as const }),
            () => ({ id: f.id, ok: false as const }),
          ),
        ),
      ).then((results) => {
        const okIds = new Set(
          results.filter((r) => r.ok).map((r) => r.id),
        );
        setFailed((f) => f.filter((x) => !okIds.has(x.id)));
      });
      reload();
    } finally {
      setRetrying(false);
    }
  }, [failed, retrying, reload]);

  // Mirar una tarjeta la registra como vista (sección Vistas) sin
  // sacarla del deck: se añade a `viewed` para conservarla tras el reload.
  useEffect(() => {
    if (viewTimer.current) window.clearTimeout(viewTimer.current);
    if (
      !current ||
      current.status !== "new" ||
      viewed.has(String(current.id)) ||
      acted.has(String(current.id))
    )
      return;
    const id = String(current.id);
    viewTimer.current = window.setTimeout(() => {
      setViewed((v) => new Set(v).add(id));
      saveInBackground(id, { status: "opened" }, "vista");
    }, VIEW_DELAY_MS);
    return () => {
      if (viewTimer.current) window.clearTimeout(viewTimer.current);
    };
  }, [current, viewed, acted, saveInBackground]);

  // Análisis perezoso: solo al expandir, una vez por oferta.
  useEffect(() => {
    if (!expanded || !current) return;
    const id = String(current.id);
    if (analyses[id] || analysisLoading === id) return;
    setAnalysisLoading(id);
    fetchJobAnalysis(current.id)
      .then((a) => setAnalyses((m) => ({ ...m, [id]: a })))
      .catch(() => {
        /* sin análisis: se muestran skills del job */
      })
      .finally(() => setAnalysisLoading((v) => (v === id ? null : v)));
  }, [expanded, current, analyses, analysisLoading]);

  // Precarga: análisis de las siguientes para que expandir sea instantáneo.
  useEffect(() => {
    for (const j of upcoming) {
      const id = String(j.id);
      if (analyses[id] || analysisFlight.current.has(id)) continue;
      analysisFlight.current.add(id);
      fetchJobAnalysis(j.id)
        .then((a) => setAnalyses((m) => ({ ...m, [id]: a })))
        .catch(() => {
          /* precarga best-effort */
        })
        .finally(() => analysisFlight.current.delete(id));
    }
  }, [upcoming, analyses]);

  // Al acabarse por decidir: una recarga (se ve "buscando") y si no hay
  // nada nuevo, mensaje de volver más tarde.
  useEffect(() => {
    if (loading || data === null) return;
    if (deck.length > 0 || unactedCount > 0) {
      emptiedRef.current = false;
      return;
    }
    if (acted.size === 0) return;
    if (emptiedRef.current) return;
    emptiedRef.current = true;
    reload();
  }, [deck.length, unactedCount, acted.size, data, loading, reload]);

  const swipe = useCallback(
    (dir: Exclude<SliceExit, null>) => {
      if (!current || exit) return;
      // Abrir PRIMERO para swipe-up (gesto del usuario): evita que el
      // bloqueador de popups intercepte la ventana (patrón de Jobs.tsx).
      if (dir === "up") window.open(current.url, "_blank", "noopener");
      const job = current;
      const id = String(job.id);
      const label =
        dir === "right" ? "guardada" : dir === "up" ? "postulación" : "descarte";
      const payload: StatusUpdatePayload =
        dir === "right"
          ? { status: "kept" }
          : dir === "up"
            ? { status: "applied", application_status: "iniciada" }
            : { status: "discarded", discard_reason: discardReason };
      // La red va por detrás: no se espera para mostrar la siguiente.
      saveInBackground(id, payload, label);
      setExit(dir);
      setExpanded(false);
      exitTimer.current = window.setTimeout(() => {
        setHistory((h) => [...h, { id, prev: job.status, dir }]);
        setActed((a) => new Set(a).add(id));
        if (dir === "right") setKept((n) => n + 1);
        else if (dir === "up") setApplied((n) => n + 1);
        else setDropped((n) => n + 1);
        // Sin mover el índice: la precargada se desliza al lugar.
        setDrag({ x: 0, y: 0, dragging: false });
        setExit(null);
      }, EXIT_MS);
    },
    [current, exit, discardReason, saveInBackground],
  );

  const keep = useCallback(() => swipe("right"), [swipe]);
  const discard = useCallback(() => swipe("left"), [swipe]);
  const apply = useCallback(() => swipe("up"), [swipe]);

  // Mirar sin decidir: avanza/retrocede sin mutar nada.
  const browse = useCallback(
    (delta: 1 | -1) => {
      if (exit || deck.length === 0) return;
      setExpanded(false);
      setDrag({ x: 0, y: 0, dragging: false });
      setIndex((i) =>
        Math.min(deck.length - 1, Math.max(0, Math.min(i, deck.length - 1) + delta)),
      );
    },
    [exit, deck.length],
  );
  const browseNext = useCallback(() => browse(1), [browse]);
  const browsePrev = useCallback(() => browse(-1), [browse]);

  const undo = useCallback(async () => {
    const last = history[history.length - 1];
    if (!last || undoBusy) return;
    setUndoBusy(true);
    try {
      await updateJobStatus(last.id, { status: last.prev });
      setActed((a) => {
        const copy = new Set(a);
        copy.delete(last.id);
        return copy;
      });
      setHistory((h) => h.slice(0, -1));
      if (last.dir === "right") setKept((n) => Math.max(0, n - 1));
      else if (last.dir === "up") setApplied((n) => Math.max(0, n - 1));
      else setDropped((n) => Math.max(0, n - 1));
      reload();
    } catch {
      setFailed((f) =>
        f.some((x) => x.id === last.id)
          ? f
          : [
              ...f,
              {
                id: last.id,
                payload: { status: last.prev },
                label: "deshacer",
              },
            ],
      );
    } finally {
      setUndoBusy(false);
    }
  }, [history, undoBusy, reload]);

  // Teclado: ← descarta, → guarda, ↑ postula, ↓ expande. Se ignoran inputs.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (!current) return;
      if (e.key === "ArrowRight") {
        e.preventDefault();
        keep();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        discard();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        apply();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setExpanded((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, apply, discard, keep]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (exit || !current) return;
    // No secuestrar scroll cuando el gesto nace dentro de la zona con
    // scroll propio (descripción expandida) o en botones/enlaces.
    const t = e.target as HTMLElement | null;
    if (t?.closest("button, a, .slice-desc.full, .slice-details")) return;
    dragStart.current = { x: e.clientX, y: e.clientY };
    setDrag((d) => ({ ...d, dragging: true }));
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.dragging || !dragStart.current) return;
    // Con touch-action:none el navegador no compite por el gesto vertical.
    if (e.cancelable) e.preventDefault();
    setDrag({
      x: e.clientX - dragStart.current.x,
      y: e.clientY - dragStart.current.y,
      dragging: true,
    });
  };

  const finishDrag = (dx: number, dy: number) => {
    dragStart.current = null;
    if (dx > SWIPE_X) {
      swipe("right");
      return;
    }
    if (dx < -SWIPE_X) {
      swipe("left");
      return;
    }
    if (dy < SWIPE_UP_Y) {
      swipe("up");
      return;
    }
    if (dy > EXPAND_Y) {
      setExpanded((v) => !v);
    }
    setDrag({ x: 0, y: 0, dragging: false });
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (!drag.dragging || !dragStart.current) return;
    // Calcular desde el evento (no del state): el último pointermove
    // puede no haber re-renderizado aún y el state quedaría una
    // fracción atrás, ignorando flicks cortos.
    const dx = e.clientX - dragStart.current.x;
    const dy = e.clientY - dragStart.current.y;
    finishDrag(dx, dy);
  };

  const onPointerCancel = (e: React.PointerEvent) => {
    // Si el navegador cancela (llamada, scroll sistema), respetar un
    // gesto ya claro en vez de tirarlo.
    if (dragStart.current) {
      const dx = e.clientX - dragStart.current.x;
      const dy = e.clientY - dragStart.current.y;
      if (Math.abs(dx) > SWIPE_X || dy < SWIPE_UP_Y || dy > EXPAND_Y) {
        finishDrag(dx, dy);
        return;
      }
    }
    dragStart.current = null;
    setDrag({ x: 0, y: 0, dragging: false });
  };

  return (
    <>
      <Header
        title="Slices"
        subtitle={
          deck.length > 0
            ? `${Math.min(safeIndex + 1, deck.length)} / ${deck.length} · ← descarta · → guarda · ↑ postula · ↓ detalles · ‹ › mirar`
            : "Solo ofertas de tus perfiles de búsqueda automática"
        }
        actions={
          history.length > 0 ? (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => void undo()}
              disabled={undoBusy}
              title="Deshacer última decisión"
            >
              <Undo2 /> Deshacer
            </button>
          ) : undefined
        }
      />
      <div className="content slices-wrap">
        {failed.length > 0 && (
          <div className="alert-error">
            No se pudo guardar {failed.length === 1 ? "una decisión" : `${failed.length} decisiones`} por red.{" "}
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => void retryFailed()}
              disabled={retrying}
            >
              {retrying ? "Reintentando…" : "Reintentar"}
            </button>
          </div>
        )}
        {(kept > 0 || dropped > 0 || applied > 0) && deck.length > 0 && (
          <p className="slices-count">
            ✅ {kept} guardadas · ❌ {dropped} descartadas · 📨 {applied}{" "}
            postuladas en esta sesión
            {remaining > 0 && remaining <= 5 && ` · Quedan ${remaining}`}
          </p>
        )}
        {loading ? (
          <LoadingState label="Buscando ofertas…" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : autoJobs.length === 0 ? (
          <EmptyState
            title="Sin ofertas de búsqueda automática."
            hint="Crea un perfil en Búsqueda con frecuencia y ejecútalo (o espera el scheduler) para traer ofertas aquí."
          />
        ) : deck.length === 0 && unactedCount > 0 ? (
          <EmptyState
            title="No hay ofertas para esos filtros."
            hint="Ajusta ciudad, match mínimo o revisa las ya decididas en Ofertas, Vistas y Descartadas."
          />
        ) : !current ? (
          <div className="card slices-done">
            <h3>Ya no hay ofertas por mostrar 🎉</h3>
            <p>
              Revisaste todo lo pendiente (✅ {kept} · ❌ {dropped} · 📨{" "}
              {applied}). Vuelve más tarde: la búsqueda automática trae más.
            </p>
            <div className="slices-done-actions">
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setIndex(0);
                  setKept(0);
                  setDropped(0);
                  setApplied(0);
                  setHistory([]);
                  setActed(new Set());
                  reload();
                }}
              >
                <RotateCcw /> Buscar de nuevo
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="toolbar slices-filters">
              <div className="toolbar-row">
                <label className="slices-filter">
                  Ciudad
                  <select
                    className="select"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                  >
                    <option value="">Todas</option>
                    {cities.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="slices-filter">
                  Orden
                  <select
                    className="select"
                    value={sort}
                    onChange={(e) => setSort(e.target.value as SortMode)}
                  >
                    <option value="found_desc">
                      Recién encontradas primero
                    </option>
                    <option value="found_asc">Antiguas primero</option>
                    <option value="match">Mejor match</option>
                  </select>
                </label>
                <label className="slices-filter">
                  Match mín.
                  <select
                    className="select"
                    value={minMatch}
                    onChange={(e) => setMinMatch(Number(e.target.value))}
                  >
                    {[0, 30, 50, 70].map((v) => (
                      <option key={v} value={v}>
                        {v === 0 ? "Todos" : `≥ ${v}%`}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="slices-check">
                  <input
                    type="checkbox"
                    checked={onlyScored}
                    onChange={(e) => setOnlyScored(e.target.checked)}
                  />{" "}
                  Solo analizadas
                </label>
              </div>
              <div className="toolbar-row">
                <label className="slices-filter">
                  Motivo descarte rápido
                  <select
                    className="select"
                    value={discardReason}
                    onChange={(e) => setDiscardReason(e.target.value)}
                  >
                    {DISCARD_REASONS.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
            <div className="slices-browser">
              <button
                className="btn btn-ghost slice-nav"
                onClick={browsePrev}
                disabled={safeIndex <= 0}
                title="Anterior (mirar sin decidir)"
                aria-label="Ver anterior sin decidir"
              >
                <ChevronLeft />
              </button>
              <div
                className="slice-deck"
                aria-live="polite"
                aria-label={`Oferta ${safeIndex + 1} de ${deck.length}: ${displayJob?.title ?? ""}`}
              >
                <div className="slice-stack">
                  {upcoming
                    .slice()
                    .reverse()
                    .map((job, i) => (
                      <div
                        key={job.id}
                        className={`slice-under slice-under-${upcoming.length - i}`}
                        aria-hidden
                      >
                        <SliceCard
                          job={job}
                          dragX={0}
                          dragY={0}
                          dragging={false}
                          exiting={null}
                          expanded={false}
                          analysis={analyses[String(job.id)] ?? null}
                          analysisLoading={false}
                          onToggleExpand={() => {}}
                        />
                      </div>
                    ))}
                  <div
                    className="slice-grip"
                    onPointerDown={onPointerDown}
                    onPointerMove={onPointerMove}
                    onPointerUp={onPointerUp}
                    onPointerCancel={onPointerCancel}
                    // Colapsada (none): el gesto vertical lo gestiona el deck
                    // (expandir); el navegador no lo roba para scroll.
                    // Expandida (pan-y): la descripción larga necesita scroll
                    // nativo en táctil; en mouse el drag sigue funcionando
                    // (touch-action no afecta al mouse) y ↓/botón colapsan.
                    style={{ touchAction: expanded ? "pan-y" : "none" }}
                  >
                    {displayJob && (
                      <SliceCard
                        key={displayJob.id}
                        job={displayJob}
                        dragX={drag.x}
                        dragY={drag.y}
                        dragging={drag.dragging}
                        exiting={exit}
                        expanded={expanded}
                        analysis={analyses[String(displayJob.id)] ?? null}
                        analysisLoading={
                          analysisLoading === String(displayJob.id)
                        }
                        onToggleExpand={() => setExpanded((v) => !v)}
                      />
                    )}
                  </div>
                </div>
              </div>
              <button
                className="btn btn-ghost slice-nav"
                onClick={browseNext}
                disabled={safeIndex >= deck.length - 1}
                title="Siguiente (mirar sin decidir)"
                aria-label="Ver siguiente sin decidir"
              >
                <ChevronRight />
              </button>
            </div>
            <div className="slice-actions">
              <button
                className="btn btn-danger-ghost slice-btn"
                onClick={discard}
                title="Descartar (←)"
              >
                <X /> Descartar
              </button>
              <button
                className="btn btn-primary slice-btn"
                onClick={apply}
                title="Abrir oferta y marcar postulada (↑)"
              >
                <Send /> Postularme
              </button>
              <button
                className="btn btn-success slice-btn"
                onClick={keep}
                title="Guardar (→)"
              >
                <Check /> Guardar
              </button>
            </div>
            <p className="slices-hint">
              Arrastra o usa ← / → / ↑ del teclado. ↓ o botón para detalles.
              ‹ › para mirar sin decidir. Mirar registra la vista en Vistas.
            </p>
          </>
        )}
      </div>
    </>
  );
}
