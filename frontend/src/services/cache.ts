// Caché en memoria para lecturas del backend (módulo aislado).
//
// Regla: al volver a una sección se pinta al instante lo guardado y NO
// se consulta al backend salvo que el dato sea viejo (TTL) o el usuario
// fuerce recarga / mute algo. Las mutaciones invalidan por prefijo.
// Solo vive en la sesión SPA (al recargar la página se vacía).

const TTL_MS = 5 * 60 * 1000;

interface Entry {
  data: unknown;
  at: number;
}

const store = new Map<string, Entry>();

export function readCache<T>(key: string): T | null {
  const entry = store.get(key);
  if (!entry) return null;
  return entry.data as T;
}

/** true si hay dato y es fresco (no necesita consulta). */
export function isFresh(key: string, ttlMs = TTL_MS): boolean {
  const entry = store.get(key);
  return !!entry && Date.now() - entry.at < ttlMs;
}

export function writeCache<T>(key: string, data: T): void {
  store.set(key, { data, at: Date.now() });
}

/** Invalida una clave exacta o todo un prefijo ("jobs:"). */
export function bustCache(keyOrPrefix: string): void {
  for (const key of [...store.keys()]) {
    if (key === keyOrPrefix || key.startsWith(keyOrPrefix)) {
      store.delete(key);
    }
  }
}
