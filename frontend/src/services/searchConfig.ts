import { api } from "./api";

export interface FitConfig {
  seniority: string | null;
  experience_years: number | null;
  salary_min_cop: number | null;
  contract_types: string[];
}

export interface FitOptions {
  seniority_levels: Array<{ id: string; label: string }>;
  experience_buckets: Array<{ years: number; label: string }>;
  salary_bands: Array<{ min_cop: number; label: string }>;
  contract_types: Array<{ id: string; label: string }>;
}

export async function fetchSearchOptions(): Promise<FitOptions> {
  const { data } = await api.get<FitOptions>("/search-config/options");
  return data;
}

export async function fetchSearchConfig(): Promise<FitConfig> {
  const { data } = await api.get<FitConfig>("/search-config");
  return data;
}

export async function updateSearchConfig(
  patch: Partial<FitConfig>,
): Promise<FitConfig> {
  const { data } = await api.put<FitConfig>("/search-config", patch);
  return data;
}
