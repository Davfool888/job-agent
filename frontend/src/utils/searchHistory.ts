// Historial de búsquedas del Dashboard (solo lectura).
// El Dashboard guarda las últimas búsquedas en localStorage bajo
// `jobagent_search_history_<uid>`; aquí se leen TODAS las de este
// navegador para sugerirlas al crear perfiles, sin tocar el Dashboard.
export interface DashboardHistoryItem {
  query: string;
  keywords: string;
  city: string;
  source: string;
  pages: number;
  maxAge: number;
  timestamp: number;
}

const PREFIX = "jobagent_search_history_";
const MAX_ITEMS = 12;

export function readDashboardHistory(): DashboardHistoryItem[] {
  const merged: DashboardHistoryItem[] = [];
  try {
    const store = window.localStorage;
    for (let i = 0; i < store.length; i++) {
      const key = store.key(i);
      if (!key || !key.startsWith(PREFIX)) continue;
      try {
        const parsed = JSON.parse(store.getItem(key) ?? "[]");
        if (Array.isArray(parsed)) {
          for (const item of parsed) {
            if (item && typeof item.query === "string" && item.query.trim()) {
              merged.push({
                query: item.query.trim(),
                keywords: typeof item.keywords === "string" ? item.keywords : "",
                city: typeof item.city === "string" ? item.city : "",
                source: typeof item.source === "string" ? item.source : "",
                pages: Number(item.pages) || 1,
                maxAge: Number(item.maxAge) || 0,
                timestamp: Number(item.timestamp) || 0,
              });
            }
          }
        }
      } catch {
        /* entrada corrupta: se ignora */
      }
    }
  } catch {
    return [];
  }
  const seen = new Set<string>();
  return merged
    .sort((a, b) => b.timestamp - a.timestamp)
    .filter((item) => {
      const key = `${item.query}‖${item.city}‖${item.source}`.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, MAX_ITEMS);
}

/** Une listas en orden (primero lo más relevante), sin duplicados. */
export function mergeOptions(...lists: string[][]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const list of lists) {
    for (const raw of list) {
      const item = (raw ?? "").trim();
      if (!item || seen.has(item.toLowerCase())) continue;
      seen.add(item.toLowerCase());
      out.push(item);
    }
  }
  return out;
}
