import { useCallback, useEffect, useState } from "react";
import {
  fetchJob,
  fetchJobDetailExtra,
  fetchJobs,
  fetchSources,
  fetchStats,
  searchJobs,
  updateJobStatus,
} from "../services/jobs";
import { fetchProfile, saveProfile } from "../services/profile";
import { fetchSearchProfiles } from "../services/searchProfiles";
import type {
  Job,
  JobDetailExtra,
  SearchResult,
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

export function useJobSearch(): {
  result: SearchResult | null;
  searching: boolean;
  searchError: string | null;
  run: (
    q: string,
    pages: number,
    details: boolean,
    source?: string,
    location?: string,
    maxAgeDays?: number,
  ) => Promise<SearchResult>;
} {
  const [result, setResult] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const run = useCallback(
    async (
      q: string,
      pages: number,
      details: boolean,
      source = "computrabajo",
      location?: string,
      maxAgeDays = 0,
    ) => {
      setSearching(true);
      setSearchError(null);
      try {
        const r = await searchJobs(q, pages, details, source, location, maxAgeDays);
        setResult(r);
        return r;
      } catch (e: unknown) {
        setSearchError(errorMessage(e));
        throw e;
      } finally {
        setSearching(false);
      }
    },
    [],
  );

  return { result, searching, searchError, run };
}

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
