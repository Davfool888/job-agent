import type { Job } from "../types/job";
import type { JobFilterState } from "../types/filters";

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

export function applyJobFilters(jobs: Job[], f: JobFilterState): Job[] {
  const text = f.text.trim().toLowerCase();
  const now = Date.now();

  const filtered = jobs.filter((j) => {
    if (
      text &&
      !`${j.title} ${j.company ?? ""} ${j.location ?? ""} ${j.description ?? ""}`
        .toLowerCase()
        .includes(text)
    ) {
      return false;
    }
    if (f.company && j.company !== f.company) return false;
    if (f.location && j.location !== f.location) return false;
    if (f.source && j.source !== f.source) return false;
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

  const byIdDesc = (a: Job, b: Job) => b.id - a.id;
  switch (f.sort) {
    case "oldest":
      return filtered.sort((a, b) => a.id - b.id);
    case "match":
      return filtered.sort(
        (a, b) => (b.match_score ?? -1) - (a.match_score ?? -1) || byIdDesc(a, b),
      );
    case "company":
      return filtered.sort((a, b) =>
        (a.company ?? "").localeCompare(b.company ?? ""),
      );
    case "title":
      return filtered.sort((a, b) => a.title.localeCompare(b.title));
    case "recent":
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
