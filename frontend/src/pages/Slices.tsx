import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, RotateCcw, Send, Undo2, X } from "lucide-react";
import { Header } from "../components/layout/Header";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { SliceCard, type SliceExit } from "../components/slices/SliceCard";
import { useJobs } from "../hooks/useApi";
import { fetchJobAnalysis } from "../services/jobs";
import { DISCARD_REASONS } from "../utils/constants";
import type { Job, JobAnalysis, JobStatus } from "../types/job";

interface HistoryEntry {
  id: string;
  prev: JobStatus;
  dir: Exclude<SliceExit, null>;
}

const SWIPE_X = 100;
const SWIPE_UP_Y = -80;
// Flick corto hacia abajo expande: 45px basta en táctil/mouse.
const EXPAND_Y = 45;

type SortMode = "recent" | "match";

export function Slices() {
  const { data, loading, error, reload, mutate } = useJobs();
  const [index, setIndex] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [drag, setDrag] = useState({ x: 0, y: 0, dragging: false });
  const [exit, setExit] = useState<SliceExit>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [kept, setKept] = useState(0);
  const [dropped, setDropped] = useState(0);
  const [applied, setApplied] = useState(0);
  // Filtros rápidos para triage: evita revisar 775 nuevas sin orden.
  const [minMatch, setMinMatch] = useState(0);
  const [onlyScored, setOnlyScored] = useState(false);
  const [sort, setSort] = useState<SortMode>("match");
  const [discardReason, setDiscardReason] = useState<string>(DISCARD_REASONS[0]);
  const [analyses, setAnalyses] = useState<Record<string, JobAnalysis>>({});
  const [analysisLoading, setAnalysisLoading] = useState<string | null>(null);
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const exitTimer = useRef<number | null>(null);

  // Solo pendientes de decisión + filtros de triage, ordenados.
  const deck = useMemo(() => {
    const base = (data ?? []).filter(
      (j) => j.status === "new" || j.status === "kept",
    );
    const filtered = base.filter((j) => {
      if (onlyScored && j.match_score === null) return false;
      if (minMatch > 0 && (j.match_score === null || j.match_score < minMatch))
        return false;
      return true;
    });
    return [...filtered].sort((a, b) =>
      sort === "match"
        ? (b.match_score ?? -1) - (a.match_score ?? -1)
        : Number(b.id) - Number(a.id),
    );
  }, [data, minMatch, onlyScored, sort]);
  const current: Job | undefined = deck[index];
  const next: Job | undefined = deck[index + 1];

  // Reset al cambiar filtros o llegar datos nuevos.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => {
    setIndex(0);
    setExpanded(false);
    setDrag({ x: 0, y: 0, dragging: false });
    setExit(null);
  }, [data, minMatch, onlyScored, sort]);

  useEffect(
    () => () => {
      if (exitTimer.current) window.clearTimeout(exitTimer.current);
    },
    [],
  );

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

  const swipe = useCallback(
    (dir: Exclude<SliceExit, null>) => {
      if (!current || busy || exit) return;
      // Abrir PRIMERO para swipe-up (gesto del usuario): evita que el
      // bloqueador de popups intercepte la ventana (patrón de Jobs.tsx).
      if (dir === "up") window.open(current.url, "_blank", "noopener");
      setExit(dir);
      setExpanded(false);
      exitTimer.current = window.setTimeout(() => {
        const job = deck[index];
        if (!job) {
          setExit(null);
          return;
        }
        setBusy(true);
        setActionError(null);
        const payload =
          dir === "right"
            ? { status: "kept" as const }
            : dir === "up"
              ? {
                  status: "applied" as const,
                  application_status: "iniciada",
                }
              : {
                  status: "discarded" as const,
                  discard_reason: discardReason,
                };
        mutate(job.id, payload).then(
          () => {
            setHistory((h) => [...h, { id: String(job.id), prev: job.status, dir }]);
            if (dir === "right") setKept((n) => n + 1);
            else if (dir === "up") setApplied((n) => n + 1);
            else setDropped((n) => n + 1);
            setIndex((i) => i + 1);
            setDrag({ x: 0, y: 0, dragging: false });
            setExit(null);
            setBusy(false);
          },
          (e: unknown) => {
            setActionError(
              e instanceof Error ? e.message : "No se pudo guardar la decisión",
            );
            setExit(null);
            setBusy(false);
          },
        );
      }, 230);
    },
    [busy, current, deck, discardReason, exit, index, mutate],
  );

  const keep = useCallback(() => swipe("right"), [swipe]);
  const discard = useCallback(() => swipe("left"), [swipe]);
  const apply = useCallback(() => swipe("up"), [swipe]);

  const undo = useCallback(async () => {
    const last = history[history.length - 1];
    if (!last || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      await mutate(last.id, { status: last.prev });
      setHistory((h) => h.slice(0, -1));
      setIndex((i) => Math.max(0, i - 1));
      if (last.dir === "right") setKept((n) => Math.max(0, n - 1));
      else if (last.dir === "up") setApplied((n) => Math.max(0, n - 1));
      else setDropped((n) => Math.max(0, n - 1));
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "No se pudo deshacer");
    } finally {
      setBusy(false);
    }
  }, [busy, history, mutate]);

  // Teclado: ← descarta, → guarda, ↑ postula, ↓ expande. Se ignoran inputs.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) return;
      if (!current || busy) return;
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
  }, [busy, current, apply, discard, keep]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (busy || exit || !current) return;
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
    // Umbral menor para expandir: el colapsado mide ~400px y antes
    // pedía 90px, demasiado para un flick corto en táctil.
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
            ? `${Math.min(index + 1, deck.length)} / ${deck.length} · ← descarta · → guarda · ↑ postula · ↓ detalles`
            : "Revisa ofertas una por una al estilo app de citas"
        }
        actions={
          history.length > 0 ? (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => void undo()}
              disabled={busy}
              title="Deshacer última decisión"
            >
              <Undo2 /> Deshacer
            </button>
          ) : undefined
        }
      />
      <div className="content slices-wrap">
        {actionError && <div className="alert-error">{actionError}</div>}
        {(kept > 0 || dropped > 0 || applied > 0) && deck.length > 0 && (
          <p className="slices-count">
            ✅ {kept} guardadas · ❌ {dropped} descartadas · 📨 {applied}{" "}
            postuladas en esta sesión
          </p>
        )}
        {loading ? (
          <LoadingState label="Cargando ofertas…" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : deck.length === 0 ? (
          <EmptyState
            title="No hay ofertas para esos filtros."
            hint="Baja el match mínimo o usa «Buscar nuevas ofertas» en el Dashboard."
          />
        ) : !current ? (
          <div className="card slices-done">
            <h3>¡Al día! 🎉</h3>
            <p>
              Revisaste las {deck.length} ofertas filtradas. ✅ {kept} · ❌{" "}
              {dropped} · 📨 {applied}.
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
                  reload();
                }}
              >
                <RotateCcw /> Recargar
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="toolbar slices-filters">
              <div className="toolbar-row">
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
                <label className="slices-filter">
                  Orden
                  <select
                    className="select"
                    value={sort}
                    onChange={(e) => setSort(e.target.value as SortMode)}
                  >
                    <option value="match">Mejor match</option>
                    <option value="recent">Recientes</option>
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
            <div
              className="slice-deck"
              aria-live="polite"
              aria-label={`Oferta ${index + 1} de ${deck.length}: ${current.title}`}
            >
              {next && (
                <div className="slice-next" aria-hidden>
                  <p className="slice-next-title">{next.title}</p>
                  <p className="slice-next-sub">
                    {next.company ?? "Empresa no indicada"} · Siguiente
                  </p>
                </div>
              )}
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
                <SliceCard
                  key={current.id}
                  job={current}
                  dragX={drag.x}
                  dragY={drag.y}
                  dragging={drag.dragging}
                  exiting={exit}
                  expanded={expanded}
                  analysis={analyses[String(current.id)] ?? null}
                  analysisLoading={analysisLoading === String(current.id)}
                  onToggleExpand={() => setExpanded((v) => !v)}
                />
              </div>
            </div>
            <div className="slice-actions">
              <button
                className="btn btn-danger-ghost slice-btn"
                onClick={discard}
                disabled={busy}
                title="Descartar (←)"
              >
                <X /> Descartar
              </button>
              <button
                className="btn btn-primary slice-btn"
                onClick={apply}
                disabled={busy}
                title="Abrir oferta y marcar postulada (↑)"
              >
                <Send /> Postularme
              </button>
              <button
                className="btn btn-success slice-btn"
                onClick={keep}
                disabled={busy}
                title="Guardar (→)"
              >
                <Check /> Guardar
              </button>
            </div>
            <p className="slices-hint">
              Arrastra o usa ← / → / ↑ del teclado. ↓ o botón para detalles.
              Arriba abre la oferta y la marca postulada.
            </p>
          </>
        )}
      </div>
    </>
  );
}
