// Servicio AISLADO de busqueda progresiva (SSE + fallback REST).
//
// Proposito: que la seccion "Buscar nuevas ofertas" del Dashboard funcione
// aunque otros componentes/servicios cambien. Reglas de aislamiento:
// - NO importa de ./jobs (evita ciclos y arrastre de cambios).
// - Solo depende de: ./api (API_URL + axios con auth), ../lib/firebase
//   (token para ?token=, porque EventSource no soporta headers) y
//   ../types/job (contrato SSE compartido con el backend).
// - Transporte primario: EventSource GET /jobs/search/stream.
// - Si el stream se corta antes de "done" (proxy/Render/Vercel, fuente
//   caida, stall), hace UN fallback automatico a GET /jobs/search (REST)
//   y sintetiza eventos started/jobs/done para que la UI se llene igual.
// - Watchdog anti-stall: los pings ": ping" del backend son comentarios
//   SSE y EventSource NO los expone a onmessage, asi que si no hay datos
//   reales en STALL_TIMEOUT_MS se asume stall y se usa el fallback.

import { API_URL, api } from "./api";
import { getFirebaseAuth, isFirebaseConfigured } from "../lib/firebase";
import type {
  SearchResult,
  StreamEvent,
  StreamJobItem,
} from "../types/job";

export interface SearchStreamParams {
  q: string;
  pages?: number;
  source?: string;
  location?: string;
  maxAgeDays?: number;
}

export type SearchStreamEvent =
  | StreamEvent
  | { type: "connection-error" };

const STALL_TIMEOUT_MS = 60000;

function buildStreamUrl(params: SearchStreamParams, idToken: string | null): string {
  const query = new URLSearchParams({
    q: params.q,
    pages: String(params.pages ?? 1),
    source: params.source ?? "computrabajo",
    ...(params.location?.trim() ? { location: params.location.trim() } : {}),
    ...(params.maxAgeDays && params.maxAgeDays > 0
      ? { max_age_days: String(params.maxAgeDays) }
      : {}),
    ...(idToken ? { token: idToken } : {}),
  });
  return `${API_URL}/jobs/search/stream?${query.toString()}`;
}

async function resolveIdToken(): Promise<string | null> {
  if (!isFirebaseConfigured) return null;
  try {
    const user = getFirebaseAuth().currentUser;
    if (!user) return null;
    return await user.getIdToken();
  } catch {
    return null;
  }
}

export function openSearchStream(
  params: SearchStreamParams,
  onEvent: (event: SearchStreamEvent) => void,
): () => void {
  let es: EventSource | null = null;
  let fallbackController: AbortController | null = null;
  let watchdog: number | null = null;
  let finished = false;
  let cancelled = false;
  let fallbackUsed = false;

  const clearWatchdog = () => {
    if (watchdog !== null) {
      window.clearTimeout(watchdog);
      watchdog = null;
    }
  };

  const cleanup = () => {
    cancelled = true;
    finished = true;
    clearWatchdog();
    es?.close();
    es = null;
    fallbackController?.abort();
  };

  const emitDoneFromRest = (result: SearchResult) => {
    if (cancelled || finished) return;
    finished = true;
    clearWatchdog();
    const items: StreamJobItem[] = result.jobs.map((j) => ({
      id: j.id,
      title: j.title,
      company: j.company,
      location: j.location,
      url: j.url,
      source: j.source,
    }));
    onEvent({
      type: "started",
      query: result.query,
      pages: result.pages,
      source: result.source,
      location: result.location,
      max_age_days: result.max_age_days,
    });
    if (items.length > 0) {
      onEvent({ type: "jobs", page: 1, jobs: items });
    }
    onEvent({
      type: "done",
      query: result.query,
      pages: result.pages,
      source: result.source,
      location: result.location,
      max_age_days: result.max_age_days,
      found: result.found,
      saved_unique: result.saved,
      analyzed: 0,
      relevant: 0,
      details_fetched: 0,
    });
  };

  // Fallback REST: misma busqueda sin streaming. Se usa UNA sola vez
  // cuando el SSE muere antes de "done". Si tambien falla, recien ahi
  // se reporta connection-error a la UI.
  const fallbackToRest = async () => {
    if (cancelled || finished || fallbackUsed) return;
    fallbackUsed = true;
    try {
      fallbackController = new AbortController();
      const { data } = await api.get<SearchResult>("/jobs/search", {
        params: {
          q: params.q,
          pages: params.pages ?? 1,
          details: false,
          source: params.source ?? "computrabajo",
          ...(params.location?.trim()
            ? { location: params.location.trim() }
            : {}),
          ...(params.maxAgeDays && params.maxAgeDays > 0
            ? { max_age_days: params.maxAgeDays }
            : {}),
        },
        signal: fallbackController.signal,
      });
      emitDoneFromRest(data);
    } catch {
      if (!cancelled && !finished) {
        finished = true;
        clearWatchdog();
        onEvent({ type: "connection-error" });
      }
    }
  };

  const armWatchdog = () => {
    clearWatchdog();
    watchdog = window.setTimeout(() => {
      // Sin datos reales en 60s: stall (scraper colgado o proxy que
      // mato el stream sin error). Cierra SSE y usa fallback REST.
      es?.close();
      es = null;
      void fallbackToRest();
    }, STALL_TIMEOUT_MS);
  };

  const connect = (idToken: string | null) => {
    if (cancelled || finished) return;
    const source = new EventSource(buildStreamUrl(params, idToken));
    es = source;
    armWatchdog();
    source.onmessage = (message) => {
      armWatchdog();
      try {
        const event = JSON.parse(message.data) as StreamEvent;
        if (event.type === "done" || event.type === "error") {
          finished = true;
          clearWatchdog();
          source.close();
        }
        onEvent(event);
      } catch {
        // Linea no-JSON: se ignora.
      }
    };
    source.onerror = () => {
      source.close();
      if (es === source) es = null;
      if (finished || cancelled) return;
      clearWatchdog();
      // Corte prematuro: intenta REST antes de rendirse.
      void fallbackToRest();
    };
  };

  // El token se resuelve async sin bloquear el retorno del cleanup.
  void resolveIdToken().then((t) => connect(t));

  return cleanup;
}
