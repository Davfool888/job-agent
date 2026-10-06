// Refleja GET/POST /search-profiles del backend.
// NO agregar campos que el backend no entregue.

export interface SearchProfile {
  id: string;
  name: string;
  title: string;
  location: string | null;
  modality: string | null;
  keywords: string[];
  sources: string[];
  active: boolean;
  frequency_minutes: number;
  // Antigüedad maxima de vacantes a traer (dias). 0 = sin limite.
  max_age_days: number;
  // Ajuste oferta<->perfil (None/[] = hereda la global). Ver search-config.
  seniority: string | null;
  experience_years: number | null;
  salary_min_cop: number | null;
  salary_max_cop: number | null;
  contract_types: string[];
  // Dueño (uid) y marca de demo (datos de prueba de invitado).
  owner_uid?: string | null;
  is_demo?: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_status: string | null;
  last_found: number;
  last_new: number;
  last_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface SearchProfileRun {
  profile_id: string;
  found: number;
  new: number;
  analyzed: number;
  relevant: number;
  errors: string[];
  fit_filtered?: Record<string, number>;
}

// CV de referencia subido al perfil (PDF). has_cv=false si no hay.
export interface ProfileCvStatus {
  profile_id: string;
  has_cv: boolean;
  filename?: string;
  size_bytes?: number;
  pages?: number;
  chars?: number;
  uploaded_at?: string | null;
  download_url?: string | null;
}

export interface SchedulerStatus {
  enabled: boolean;
  configured: boolean;
  interval_seconds: number;
  running_profiles: string[];
  last_tick: {
    at: string | null;
    profiles: number;
    new: number;
    error: string | null;
  };
}

export const EMPTY_SEARCH_PROFILE = {
  name: "",
  title: "",
  location: "",
  modality: "",
  keywords: [] as string[],
  sources: [] as string[],
  active: true,
  frequency_minutes: 10,
};
