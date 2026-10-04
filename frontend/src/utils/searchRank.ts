// Ranking de relevancia para el buscador general del Dashboard.
//
// El backend trae ofertas por cargo desde cada central; aqui se ordenan
// y agrupan por afinidad con lo escrito: el cargo manda (señal
// primaria) y las palabras clave acercan puestos relacionados
// (señal secundaria). Puro y testeable: no depende de React.
import type { StreamJobItem } from "../types/job";

export type MatchTier = "exact" | "related" | "other";

export interface RankedJob {
  job: StreamJobItem;
  score: number;
  tier: MatchTier;
  hits: string[];
}

const STOPWORDS = new Set([
  "de", "la", "el", "los", "las", "en", "y", "con", "para", "por",
  "del", "al", "un", "una", "se", "que", "como",
]);

export function normText(value: string | null | undefined): string {
  return (value ?? "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9ñ\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function tokensOf(text: string): string[] {
  return normText(text)
    .split(" ")
    .filter((t) => t.length > 2 && !STOPWORDS.has(t));
}

function includesToken(haystack: string, token: string): boolean {
  if (!token) return false;
  if (haystack === token) return true;
  // Prefijo para flexiones (abogado/abogada, ingeniero/ingenieria).
  const stem = token.length > 5 ? token.slice(0, -1) : token;
  return haystack.split(" ").some(
    (w) => w === token || (stem.length > 3 && w.startsWith(stem)),
  );
}

export function scoreJob(
  job: StreamJobItem,
  queryTokens: string[],
  keywordTokens: string[],
): { score: number; tier: MatchTier; hits: string[] } {
  const title = normText(job.title);
  const extra = normText(
    `${job.company ?? ""} ${job.location ?? ""}`,
  );
  const hits: string[] = [];
  let score = 0;

  let queryHits = 0;
  for (const tok of queryTokens) {
    if (includesToken(title, tok)) {
      queryHits += 1;
      score += 3;
      hits.push(tok);
    } else if (extra && includesToken(extra, tok)) {
      queryHits += 0.5;
      score += 1;
      hits.push(tok);
    }
  }
  let keywordHits = 0;
  for (const tok of keywordTokens) {
    if (queryTokens.includes(tok)) continue;
    if (includesToken(title, tok) || includesToken(extra, tok)) {
      keywordHits += 1;
      score += 2;
      if (!hits.includes(tok)) hits.push(tok);
    }
  }

  let tier: MatchTier = "other";
  if (queryTokens.length > 0 && queryHits >= queryTokens.length) {
    tier = "exact";
    score += 5;
  } else if (queryHits > 0 || keywordHits > 0) {
    tier = "related";
  }
  return { score, tier, hits };
}

export function rankJobs(
  jobs: StreamJobItem[],
  query: string,
  keywords: string,
): RankedJob[] {
  const queryTokens = tokensOf(query);
  const keywordTokens = tokensOf(keywords);
  return jobs
    .map((job) => ({
      job,
      ...scoreJob(job, queryTokens, keywordTokens),
    }))
    .sort((a, b) => b.score - a.score || a.job.title.localeCompare(b.job.title));
}

export function splitKeywords(raw: string): string[] {
  return raw
    .split(/[,;\n]+/)
    .map((k) => k.trim())
    .filter(Boolean);
}
