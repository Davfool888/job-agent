import { useCallback, useEffect, useState } from "react";
import {
  fetchJob,
  fetchJobDetailExtra,
  fetchJobs,
  fetchSources,
  fetchStats,
  updateJobStatus,
} from "../services/jobs";
import { bustCache, isFresh, readCache, writeCache } from "../services/cache";
// Hook de busqueda progresiva aislado en su propio modulo. Se re-exporta
// aqui por compatibilidad; el Dashboard debe importar de
// ../hooks/useJobSearchStream para no acoplarse a este archivo.
export { useJobSearchStream } from "./useJobSearchStream";
export type { LiveSearchState } from "./useJobSearchStream";
import { fetchProfile, saveProfile } from "../services/profile";
import { fetchSearchProfiles } from "../services/searchProfiles";
import type {
  Job,
  JobDetailExtra,
  StatsSummary,
  StatusUpdatePayload,
} from "../types/job";
import type { Profile } from "../types/profile";

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

function errorMessage(e: unknown): string {
  // Prefiere el detalle que devuelve FastAPI (HTTPException.detail).
  if (
    typeof e === "object" &&
    e !== null &&
    "response" in e &&
    typeof (e as { response?: unknown }).response === "object"
  ) {
    const data = (e as { response: { data?: unknown } }).response.data as
      | { detail?: unknown }
      | undefined;
    if (data && typeof data.detail === "string" && data.detail) {
      return data.detail;
    }
  }
  if (e instanceof Error) return e.message;
  return "Error inesperado";
}

function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[],
  cacheKey?: string,
): AsyncState<T> {
  const [data, setData] = useState<T | null>(() =>
    cacheKey ? readCache<T>(cacheKey) : null,
  );
  // Con dato guardado fresco se pinta al instante sin spinner ni consulta.
  const [loading, setLoading] = useState<boolean>(() =>
    cacheKey ? !isFresh(cacheKey) : true,
  );
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    // Dato fresco en caché: no se consulta al backend en este montaje.
    if (cacheKey && isFresh(cacheKey) && tick === 0) {
      setLoading(false);
      return () => {
        alive = false;
      };
    }
    if (!cacheKey || readCache(cacheKey) === null) {
      setLoading(true);
    }
    fn()
      .then((d) => {
        if (!alive) return;
        if (cacheKey) writeCache(cacheKey, d);
        setData(d);
      })
      .catch((e: unknown) => {
        // Con dato guardado se conserva la lista y no se muestra error:
        // el reintento ocurre en la próxima visita con caché vencida.
        if (alive && (cacheKey ? readCache(cacheKey) === null : true)) {
          setError(errorMessage(e));
        }
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => {
    if (cacheKey) bustCache(cacheKey);
    setLoading(true);
    setError(null);
    setTick((t) => t + 1);
  }, [cacheKey]);
  return { data, loading, error, reload };
}

export function useJobs(status?: string): AsyncState<Job[]> & {
  mutate: (id: number | string, payload: StatusUpdatePayload) => Promise<Job>;
} {
  const cacheKey = `jobs:${status ?? "all"}`;
  const state = useAsync(() => fetchJobs(500, status), [status], cacheKey);

  const mutate = useCallback(
    async (id: number | string, payload: StatusUpdatePayload) => {
      const updated = await updateJobStatus(id, payload);
      // El cambio de estado mueve la oferta de sección: invalida todas
      // las listas y recarga esta.
      bustCache("jobs:");
      state.reload();
      return updated;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [state.reload],
  );

  return { ...state, mutate };
}

export function useJob(id: number | string): AsyncState<Job> {
  return useAsync(() => fetchJob(id), [id], `job:${id}`);
}

export function useJobExtra(id: number | string): AsyncState<JobDetailExtra> {
  return useAsync(() => fetchJobDetailExtra(id), [id], `jobextra:${id}`);
}

export function useStats(refreshKey = 0): AsyncState<StatsSummary> {
  // La llave incluye refreshKey: un cambio fuerza consulta aunque haya
  // caché (tras buscar/analizar los totales cambian).
  return useAsync(fetchStats, [refreshKey], `stats:${refreshKey}`);
}

export function useProfile(): AsyncState<Profile> & {
  save: (p: Profile) => Promise<Profile>;
  saving: boolean;
} {
  const state = useAsync(fetchProfile, [], "profile");
  const [saving, setSaving] = useState(false);

  const save = useCallback(async (p: Profile) => {
    setSaving(true);
    try {
      const saved = await saveProfile(p);
      writeCache("profile", saved);
      return saved;
    } finally {
      setSaving(false);
    }
  }, []);

  return { ...state, save, saving };
}

// NOTE: useJobSearchStream vive en ./useJobSearchStream (modulo aislado).
// Se re-exporta arriba por compatibilidad.

export function useSources(): {
  sources: string[];
  loading: boolean;
} {
  const [sources, setSources] = useState<string[]>(() => readCache<string[]>("sources") ?? []);
  const [loading, setLoading] = useState<boolean>(() => !isFresh("sources"));

  useEffect(() => {
    let alive = true;
    if (isFresh("sources")) {
      setLoading(false);
      return () => {
        alive = false;
      };
    }
    fetchSources()
      .then((s) => {
        if (!alive) return;
        writeCache("sources", s);
        setSources(s);
      })
      .catch(() => alive && readCache<string[]>("sources") === null && setSources(["computrabajo"]))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  return { sources, loading };
}

export function useProfileOptions(): Array<{ id: string; name: string }> {
  const [profiles, setProfiles] = useState<Array<{ id: string; name: string }>>(
    () => readCache<Array<{ id: string; name: string }>>("profiles-min") ?? [],
  );

  useEffect(() => {
    let alive = true;
    if (isFresh("profiles-min")) return () => {
      alive = false;
    };
    fetchSearchProfiles()
      .then((list) => {
        if (!alive) return;
        const mapped = list.map((p) => ({ id: String(p.id), name: p.name }));
        writeCache("profiles-min", mapped);
        setProfiles(mapped);
      })
      .catch(() => {
        if (alive && readCache("profiles-min") === null) setProfiles([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  return profiles;
}
