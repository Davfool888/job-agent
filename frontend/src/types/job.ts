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
  location?: string | null;
  max_age_days?: number;
  found: number;
  filtered_out?: number;
  fit_filtered?: Record<string, number>;
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

// Eventos de GET /jobs/search/stream (Server-Sent Events).
export interface StreamJobItem {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  url: string;
  source: string;
}

export type StreamEvent =
  | { type: "started"; query: string; pages: number; source: string;
      location?: string | null; max_age_days?: number }
  | { type: "jobs"; page: number; jobs: StreamJobItem[] }
  | { type: "analyzing"; count: number }
  | { type: "done"; query: string; pages: number; source: string;
      location?: string | null; max_age_days?: number; found: number;
      saved_unique: number; analyzed: number; relevant: number;
      details_fetched: number; fit_filtered?: Record<string, number>;
      analysis_error?: string }
  | { type: "error"; message: string };

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

// Evaluación legible oferta-vs-perfil (GET /jobs/{id}/analysis).
// Refleja backend/app/analysis/verdict.py; todo opcional salvo level.
export interface FitSkillGroup {
  matched: string[];
  missing: string[];
  coverage: number | null;
}

export interface FitExperience {
  required_years: number | null;
  profile_years: number | null;
  fit: "sobrado" | "justo" | "corto" | "exento" | "sin_dato";
  note: string;
}

export interface FitRole {
  category: string | null;
  detected_role: string | null;
  target_roles: string[];
  match: boolean | null;
  matched_target: string | null;
  note: string;
}

export interface FitReport {
  level: string;
  label: string;
  score: number | null;
  dimensions: {
    tecnicas: FitSkillGroup;
    blandas: FitSkillGroup;
    experiencia: FitExperience;
    puesto: FitRole;
    contenido: Record<string, number | null>;
  };
  profile_snapshot: {
    technical_skills: string[];
    soft_skills: string[];
    years_experience: number | null;
    target_roles: string[];
  };
  strengths: string[];
  gaps: string[];
  reasons: string[];
}

export interface JobAnalysis {
  job_id: string;
  match_score: number | null;
  detected_role: string | null;
  category: string | null;
  evidence: string[];
  matching_skills: string[];
  missing_skills: string[];
  discovered_by: string[];
  experience_required: string | null;
  analyzed: boolean;
  fit_report?: FitReport | null;
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
