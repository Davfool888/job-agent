import { useCallback, useEffect, useState } from "react";
import {
  fetchJob,
  fetchJobDetailExtra,
  fetchJobs,
  fetchSources,
  fetchStats,
  updateJobStatus,
} from "../services/jobs";
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

function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    fn()
      .then((d) => alive && setData(d))
      .catch((e: unknown) => alive && setError(errorMessage(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    setTick((t) => t + 1);
  }, []);
  return { data, loading, error, reload };
}

export function useJobs(status?: string): AsyncState<Job[]> & {
  mutate: (id: number | string, payload: StatusUpdatePayload) => Promise<Job>;
} {
  const state = useAsync(() => fetchJobs(500, status), [status]);

  const mutate = useCallback(
    async (id: number | string, payload: StatusUpdatePayload) => {
      const updated = await updateJobStatus(id, payload);
      state.reload();
      return updated;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [state.reload],
  );

  return { ...state, mutate };
}

export function useJob(id: number | string): AsyncState<Job> {
  return useAsync(() => fetchJob(id), [id]);
}

export function useJobExtra(id: number | string): AsyncState<JobDetailExtra> {
  return useAsync(() => fetchJobDetailExtra(id), [id]);
}

export function useStats(refreshKey = 0): AsyncState<StatsSummary> {
  return useAsync(fetchStats, [refreshKey]);
}

export function useProfile(): AsyncState<Profile> & {
  save: (p: Profile) => Promise<Profile>;
  saving: boolean;
} {
  const state = useAsync(fetchProfile, []);
  const [saving, setSaving] = useState(false);

  const save = useCallback(async (p: Profile) => {
    setSaving(true);
    try {
      return await saveProfile(p);
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
  const [sources, setSources] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    fetchSources()
      .then((s) => alive && setSources(s))
      .catch(() => alive && setSources(["computrabajo"]))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  return { sources, loading };
}

export function useProfileOptions(): Array<{ id: string; name: string }> {
  const [profiles, setProfiles] = useState<Array<{ id: string; name: string }>>(
    [],
  );

  useEffect(() => {
    let alive = true;
    fetchSearchProfiles()
      .then((list) => {
        if (alive) {
          setProfiles(list.map((p) => ({ id: String(p.id), name: p.name })));
        }
      })
      .catch(() => {
        if (alive) setProfiles([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  return profiles;
}
