import { API_URL, api } from "./api";
import { getFirebaseAuth, isFirebaseConfigured } from "../lib/firebase";
import type {
  Job,
  JobDetailExtra,
  SearchResult,
  StatsSummary,
  StatusUpdatePayload,
  StreamEvent,
} from "../types/job";

export async function fetchJobs(
  limit = 200,
  status?: string,
): Promise<Job[]> {
  const { data } = await api.get<Job[]>("/jobs", {
    params: { limit, ...(status ? { status } : {}) },
  });
  return data;
}

export async function fetchJob(id: number | string): Promise<Job> {
  const { data } = await api.get<Job>(`/jobs/${id}`);
  return data;
}

export async function fetchJobDetailExtra(
  id: number | string,
): Promise<JobDetailExtra> {
  const { data } = await api.get<JobDetailExtra>(`/jobs/${id}/detail`);
  return data;
}

export async function searchJobs(
  q: string,
  pages = 1,
  details = false,
  source = "computrabajo",
  location?: string,
  maxAgeDays = 0,
): Promise<SearchResult> {
  const { data } = await api.get<SearchResult>("/jobs/search", {
    params: {
      q,
      pages,
      details,
      source,
      ...(location?.trim() ? { location: location.trim() } : {}),
      ...(maxAgeDays > 0 ? { max_age_days: maxAgeDays } : {}),
    },
  });
  return data;
}

export interface StreamSearchParams {
  q: string;
  pages?: number;
  source?: string;
  location?: string;
  maxAgeDays?: number;
}

// Busqueda progresiva (SSE): llama onEvent por cada pagina guardada.
// Devuelve funcion para cancelar. Al cerrar limpio tras "done" no hay
// error; si el servidor corta antes, llega error de conexion.
//
// Nota: EventSource no soporta headers, por eso el token va como ?token=
// (el backend lo acepta). Como la funcion debe devolver el cleanup de
// forma sincrona, el token se resuelve por promesa y la conexion se abre
// al resolver — sin usar `await` en funcion sync (rompia `tsc -b`).
export function streamSearchJobs(
  params: StreamSearchParams,
  onEvent: (event: StreamEvent | { type: "connection-error" }) => void,
): () => void {
  let source: EventSource | null = null;
  let finished = false;
  let cancelled = false;

  const cleanup = () => {
    cancelled = true;
    finished = true;
    source?.close();
  };

  const connect = (idToken: string | null) => {
    if (cancelled) return;
    const query = new URLSearchParams({
      q: params.q,
      pages: String(params.pages ?? 1),
      source: params.source ?? "computrabajo",
      ...(params.location?.trim()
        ? { location: params.location.trim() }
        : {}),
      ...(params.maxAgeDays && params.maxAgeDays > 0
        ? { max_age_days: String(params.maxAgeDays) }
        : {}),
      ...(idToken ? { token: idToken } : {}),
    });
    const es = new EventSource(
      `${API_URL}/jobs/search/stream?${query.toString()}`,
    );
    source = es;
    es.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as StreamEvent;
        if (event.type === "done" || event.type === "error") {
          finished = true;
          es.close();
        }
        onEvent(event);
      } catch {
        // Linea no-JSON (ping ": ..."): se ignora.
      }
    };
    es.onerror = () => {
      es.close();
      if (!finished) {
        onEvent({ type: "connection-error" });
      }
    };
  };

  // Resolver token sin bloquear el retorno del cleanup.
  if (isFirebaseConfigured) {
    try {
      const user = getFirebaseAuth().currentUser;
      if (user) {
        user
          .getIdToken()
          .then((t) => connect(t))
          .catch(() => connect(null));
        return cleanup;
      }
    } catch {
      /* sin auth: sigue sin token */
    }
  }
  connect(null);
  return cleanup;
}

export async function fetchSources(): Promise<string[]> {
  const { data } = await api.get<{ sources: string[] }>("/sources");
  return data.sources;
}

export async function updateJobStatus(
  id: number | string,
  payload: StatusUpdatePayload,
): Promise<Job> {
  const { data } = await api.patch<Job>(`/jobs/${id}/status`, payload);
  return data;
}

export interface AnalysisResult {
  match_score: number;
  detected_role: string | null;
  category: string;
  evidence: string[];
  matched_skills: string[];
  missing_skills: string[];
  experience_required: string | null;
  role_matches_goal: boolean;
  score_breakdown: {
    title: number;
    skills: number;
    responsibilities: number;
    tools: number;
  };
}

export async function analyzeJob(
  id: number | string,
): Promise<{ job: Job; analysis: AnalysisResult }> {
  const { data } = await api.post(`/jobs/${id}/analyze`);
  return data;
}

export interface DiscoverSummary {
  source: string;
  queries_run: number;
  queries_failed: number;
  found: number;
  saved_unique: number;
  details_fetched: number;
  analyzed: number;
  relevant: number;
  per_query: Array<{ query: string; found: number; saved: number }>;
  errors: Array<{ query: string; error: string }>;
}

export async function discoverJobs(payload: {
  source?: string;
  packs?: string[];
  queries?: string[];
  pages?: number;
  max_details?: number;
}): Promise<DiscoverSummary> {
  const { data } = await api.post<DiscoverSummary>("/jobs/discover", payload);
  return data;
}

export async function fetchDiscoveryPacks(): Promise<
  Record<string, string[]>
> {
  const { data } = await api.get<{ packs: Record<string, string[]> }>(
    "/discovery/packs",
  );
  return data.packs;
}

export async function fetchStats(): Promise<StatsSummary> {
  const { data } = await api.get<StatsSummary>("/stats");
  return data;
}

export async function checkHealth(): Promise<boolean> {
  try {
    const { data } = await api.get("/health");
    return data?.status === "ok";
  } catch {
    return false;
  }
}
