import type { Job } from "../types/job";
import type { JobFilterState } from "../types/filters";
import { normText, uniqueCanonicalLocations } from "./profileOptions";

// Filtrado y ordenamiento en cliente sobre datos reales del backend.
// (El backend expone /jobs?status=&limit=; los filtros finos viven aqui
// hasta que exista un endpoint de busqueda avanzada.)

// Fecha de referencia de una oferta: publicación real si existe,
// si no, cuándo la encontramos.
export function referenceDate(j: Job): string {
  return j.published_at ?? j.created_at;
}

export function ageInDays(j: Job, now = Date.now()): number {
  const t = new Date(referenceDate(j)).getTime();
  if (Number.isNaN(t)) return Infinity;
  return (now - t) / 86400000;
}

export function isSameLocalDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function postedToday(j: Job, now = new Date()): boolean {
  const t = new Date(referenceDate(j));
  if (Number.isNaN(t.getTime())) return false;
  return isSameLocalDay(t, now);
}

/**
 * La ubicacion del filtro es canonica ("Bogotá"), pero el scraper guarda
 * variantes ("Bogotá, D.C., Bogotá, D.C."). Sin normalizar, elegir Bogotá
 * en el filtro ocultaba ofertas que si están en Bogotá.
 */
function locationMatches(
  jobLocation: string | null | undefined,
  filterLocation: string,
): boolean {
  const wanted = normText(filterLocation);
  if (!wanted) return true;
  const actual = normText(jobLocation);
  if (!actual) return false;
  if (actual === wanted) return true;
  // Compara por la parte inicial antes de la primera coma.
  const head = (v: string) => v.split(",")[0].trim();
  if (head(actual) === wanted) return true;
  // "bogota" dentro de "bogota d c" y variantes de sufijos.
  return actual.startsWith(`${wanted} `);
}

export function applyJobFilters(jobs: Job[], f: JobFilterState): Job[] {
  const text = f.text.trim().toLowerCase();
  const now = Date.now();

  const filtered = jobs.filter((j) => {
    if (text) {
      // Texto libre: cargo, empresa, ciudad, descripcion y señales del
      // analisis (skills como DAX/Python, rol detectado, query origen).
      const haystack = [
        j.title,
        j.company ?? "",
        j.location ?? "",
        j.description ?? "",
        j.search_query ?? "",
        j.detected_role ?? "",
        j.category ?? "",
        ...(j.evidence ?? []),
        ...(j.matched_skills ?? []),
        ...(j.missing_skills ?? []),
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(text)) {
        return false;
      }
    }
    if (f.company && j.company !== f.company) return false;
    if (f.location && !locationMatches(j.location, f.location)) return false;
    if (f.source && j.source !== f.source) return false;
    if (
      f.profile &&
      !(j.search_profile_ids ?? []).map(String).includes(f.profile)
    )
      return false;
    if (f.onlyScored && j.match_score === null) return false;
    if (
      f.minMatch > 0 &&
      (j.match_score === null || j.match_score < f.minMatch)
    ) {
      return false;
    }
    if (f.maxAgeDays === 1) {
      // "Hoy": día calendario, no últimas 24h.
      if (!postedToday(j, new Date(now))) return false;
    } else if (f.maxAgeDays > 1 && ageInDays(j, now) > f.maxAgeDays) {
      return false;
    }
    if (f.onlyReposted && (j.times_seen ?? 1) < 2) return false;
    return true;
  });

  const byIdDesc = (a: Job, b: Job) => Number(b.id) - Number(a.id);
  const byFoundDesc = (a: Job, b: Job) =>
    new Date(b.found_at ?? b.created_at).getTime() -
    new Date(a.found_at ?? a.created_at).getTime();
  switch (f.sort) {
    case "oldest":
      return filtered.sort((a, b) => Number(a.id) - Number(b.id));
    case "match":
      return filtered.sort(
        (a, b) => (b.match_score ?? -1) - (a.match_score ?? -1) || byIdDesc(a, b),
      );
    case "match_asc":
      return filtered.sort(
        (a, b) => (a.match_score ?? 101) - (b.match_score ?? 101) || byIdDesc(a, b),
      );
    case "company":
      return filtered.sort((a, b) =>
        (a.company ?? "").localeCompare(b.company ?? ""),
      );
    case "title":
      return filtered.sort((a, b) => a.title.localeCompare(b.title));
    case "recent":
      return filtered.sort(byIdDesc);
    case "found":
      return filtered.sort(byFoundDesc);
    default:
      return filtered.sort(byIdDesc);
  }
}

export function uniqueSorted(
  jobs: Job[],
  pick: (j: Job) => string | null,
): string[] {
  const set = new Set<string>();
  for (const j of jobs) {
    const v = (pick(j) ?? "").trim();
    if (v) set.add(v);
  }
  return [...set].sort((a, b) => a.localeCompare(b));
}

/**
 * Ubicaciones para el filtro: colapsa las variantes del scraper
 * ("Bogotá, D.C., Bogotá, D.C.", "Bogotá") en una sola opción.
 */
export function uniqueLocations(jobs: Job[]): string[] {
  return uniqueCanonicalLocations(jobs.map((j) => j.location));
}

export interface ProfileOption {
  id: string;
  name: string;
  count: number;
}

// Perfiles que encontraron las ofertas visibles (para el filtro).
export function profileOptions(
  jobs: Job[],
  profiles: Array<{ id: string | number; name: string }>,
): ProfileOption[] {
  const counts = new Map<string, number>();
  for (const j of jobs) {
    for (const pid of j.search_profile_ids ?? []) {
      const key = String(pid);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  const names = new Map(profiles.map((p) => [String(p.id), p.name]));
  return [...counts.entries()]
    .map(([id, count]) => ({
      id,
      name: names.get(id) ?? `Perfil ${id}`,
      count,
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}
