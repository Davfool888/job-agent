// Tipos generados a partir del backend real:
// backend/app/schemas/job.py (JobResponse) y
// backend/app/database/models.py (JOB_STATUSES).
// NO agregar campos que el backend no entregue.

export type JobStatus =
  | "new"
  | "kept"
  | "discarded"
  | "opened"
  | "applied";

export interface Job {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  url: string;
  description: string | null;
  source: string;
  search_query: string | null;
  created_at: string;
  status: JobStatus;
  discard_reason: string | null;
  discard_note: string | null;
  decided_at: string | null;
  applied_at: string | null;
  application_status: string | null;
  // Los escribe el agente cuando exista. `null` = sin analizar.
  match_score: number | null;
  matched_skills: string[];
  missing_skills: string[];
  // Fecha real de publicación extraída de cada fuente (null = no disponible).
  published_text: string | null;
  published_at: string | null;
  // Republicación: misma oferta (título+empresa+ubicación) con otra URL.
  fingerprint: string | null;
  times_seen: number;
  last_seen_at: string | null;
  // Análisis por capas (backend/app/analysis). null = sin analizar.
  detected_role: string | null;
  category: string | null;
  evidence: string[];
  discovered_by: string[];
  experience_required: string | null;
  role_matches_goal?: boolean | null;
  // CV asociado (§10-§13).
  cv_generated?: boolean | null;
  cv_path?: string | null;
  // Busqueda automatica: perfiles que encontraron la oferta + fechas.
  search_profile_ids: string[];
  found_at: string | null;
  first_seen_at: string | null;
}

export interface SearchResult {
  query: string;
  pages: number;
  source: string;
  found: number;
  saved: number;
  jobs: Array<{
    id: string;
    title: string;
    company: string | null;
    location: string | null;
    url: string;
    source: string;
    description: string | null;
  }>;
}

export interface JobDetailExtra {
  id: string;
  title: string;
  company?: string | null;
  location?: string | null;
  url: string;
  description: string | null;
  tags?: string[];
  requirements?: string[];
  skills?: string[];
  cached: boolean;
}

export interface StatusUpdatePayload {
  status: JobStatus;
  discard_reason?: string | null;
  discard_note?: string | null;
  application_status?: string | null;
}

export interface StatsSummary {
  total: number;
  by_status: Record<string, number>;
  scored_count: number;
  avg_match: number | null;
  top_companies: Array<{ company: string; count: number }>;
  top_queries: Array<{ query: string; count: number }>;
  discard_reasons: Array<{ reason: string; count: number }>;
  last_job: {
    id: string;
    title: string;
    company: string | null;
    created_at: string | null;
  } | null;
}
