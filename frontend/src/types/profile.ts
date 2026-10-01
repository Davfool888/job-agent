// Refleja backend/app/services/job_service.py::DEFAULT_PROFILE.
// El agente usara estos datos para el analisis de coincidencia.

export interface Profile {
  full_name: string;
  title: string;
  location: string;
  linkedin: string;
  github: string;
  portfolio: string;
  skills: string[];
  target_roles: string[];
  sectors: string[];
  modality: string;
  preferred_location: string;
  min_salary: string;
  experience_level: string;
  // Origen de los datos (backend): admin = perfil base global,
  // own = perfil personal del usuario, demo = datos de prueba de
  // invitado, shared = modo sin sesion.
  scope?: "admin" | "own" | "demo" | "shared";
}

// Ciudad normalizada (GET /catalogs). Guardar siempre el id.
export interface CityOption {
  id: string;
  label: string;
  country: string;
}

// Entrada de idioma con niveles por habilidad (A1-C2/Nativo).
export interface LanguageEntry {
  id: string;
  language: string | null;
  language_label: string;
  academy: string;
  level: string | null;
  listening: string | null;
  reading: string | null;
  writing: string | null;
  speaking: string | null;
}

// Perfil modular con perspectivas (GET/PUT /profile/full).
// Cada entrada (experiencia, educacion, proyecto, certificacion)
// puede tener N perspectivas: distintas formas de presentar los
// mismos hechos reales segun el tipo de vacante.
export interface Perspective {
  id: string;
  label: string;
  description: string;
  skills: string[];
  tools: string[];
  domains: string[];
  roles: string[];
}

export interface CityRef {
  id: string;
  label: string;
  country: string | null;
}

export interface CatalogItem {
  id: string;
  label: string;
  hint?: string;
}

export interface CityOption extends CatalogItem {
  country: string;
}

export interface Catalogs {
  professional_titles: CatalogItem[];
  modalities: CatalogItem[];
  education_levels: CatalogItem[];
  entry_status: CatalogItem[];
  languages: CatalogItem[];
  language_levels: CatalogItem[];
  contract_types: CatalogItem[];
  countries: CatalogItem[];
  cities: CityOption[];
}

export interface ProfileEntry {
  id?: string;
  title?: string;
  name?: string;
  degree?: string;
  company?: string;
  institution?: string;
  period?: string;
  // Estructurados (fechas ISO YYYY-MM-DD, null si no aplica).
  start_date?: string | null;
  end_date?: string | null;
  is_current?: boolean;
  modality?: string | null;
  city?: CityRef | null;
  description?: string;
  contract_type?: string | null;
  level?: string | null;
  status?: string | null;
  url?: string | null;
  repo?: string | null;
  technologies?: string[];
  technical_skills?: string[];
  soft_skills?: string[];
  // Certificaciones.
  issued_date?: string | null;
  expiry_date?: string | null;
  credential_id?: string;
  credential_url?: string;
  facts?: string;
  perspectives: Perspective[];
}

export interface RichProfile {
  personal: Record<string, string>;
  professional_summary: string;
  years_experience: number | null;
  technical_skills: string[];
  soft_skills: string[];
  experience: ProfileEntry[];
  education: ProfileEntry[];
  projects: ProfileEntry[];
  certifications: ProfileEntry[];
  skills: Record<string, string[]>;
  languages: LanguageEntry[];
  target_roles: string[];
  _warnings?: string[];
}

export interface TailoredBlock {
  section: string;
  item: string;
  organization: string;
  perspective: string;
  description: string;
  skills: string[];
  tools: string[];
  relevance_score: number;
  matched_skills: string[];
  matched_domain: string[];
}

export interface TailorResult {
  job_id: number | string;
  analysis: {
    match_score: number | null;
    detected_role: string | null;
    category: string | null;
    evidence: string[];
    perspective_bonus: number;
  };
  selection: Array<
    TailoredBlock & {
      perspective_id: string;
      section: string;
      item_index: number;
      item_title: string;
      item_org: string;
      breakdown: Record<string, number>;
    }
  >;
  combined_skills: string[];
  tailored_profile: {
    adapted: boolean;
    job_title: string;
    personal: Record<string, string>;
    blocks: TailoredBlock[];
    combined_skills: string[];
  };
}

export const EMPTY_PROFILE: Profile = {
  full_name: "",
  title: "",
  location: "",
  linkedin: "",
  github: "",
  portfolio: "",
  skills: [],
  target_roles: [],
  sectors: [],
  modality: "",
  preferred_location: "",
  min_salary: "",
  experience_level: "",
};
