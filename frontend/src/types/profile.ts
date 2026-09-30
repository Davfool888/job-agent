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

export interface ProfileEntry {
  id?: string;
  title?: string;
  name?: string;
  degree?: string;
  company?: string;
  institution?: string;
  period?: string;
  facts?: string;
  description?: string;
  perspectives: Perspective[];
}

export interface RichProfile {
  personal: Record<string, string>;
  professional_summary: string;
  experience: ProfileEntry[];
  education: ProfileEntry[];
  projects: ProfileEntry[];
  certifications: ProfileEntry[];
  skills: Record<string, string[]>;
  languages: string[];
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
