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
