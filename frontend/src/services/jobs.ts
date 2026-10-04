import { api } from "./api";
import { openSearchStream } from "./searchStream";
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
// Devuelve funcion para cancelar.
//
// Implementacion real aislada en ./searchStream (SSE + fallback REST):
// este wrapper solo existe por compatibilidad con imports existentes.
export function streamSearchJobs(
  params: StreamSearchParams,
  onEvent: (event: StreamEvent | { type: "connection-error" }) => void,
): () => void {
  return openSearchStream(params, onEvent);
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
