export interface JobFilterState {
  text: string;
  company: string;
  location: string;
  source: string;
  minMatch: number; // 0 = sin filtro
  onlyScored: boolean;
  // Antigüedad de la publicación (usa published_at, con fallback a created_at).
  maxAgeDays: number; // 0 = sin filtro, 1 = hoy, 3, 7...
  onlyReposted: boolean;
  sort: "recent" | "oldest" | "match" | "company" | "title" | "found";
}

export const DEFAULT_FILTERS: JobFilterState = {
  text: "",
  company: "",
  location: "",
  source: "",
  minMatch: 0,
  onlyScored: false,
  maxAgeDays: 0,
  onlyReposted: false,
  sort: "recent",
};
