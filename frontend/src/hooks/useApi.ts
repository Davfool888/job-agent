import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchJob,
  fetchJobDetailExtra,
  fetchJobs,
  fetchSources,
  fetchStats,
  streamSearchJobs,
  updateJobStatus,
} from "../services/jobs";
import { fetchProfile, saveProfile } from "../services/profile";
import { fetchSearchProfiles } from "../services/searchProfiles";
import type {
  Job,
  JobDetailExtra,
  StatsSummary,
  StatusUpdatePayload,
  StreamJobItem,
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

export interface LiveSearchState {
  jobs: StreamJobItem[];
  page: number;
  pages: number;
  found: number;
  analyzing: boolean;
  searching: boolean;
  done: boolean;
  cancelled: boolean;
  searchError: string | null;
  summary: {
    query: string;
    source: string;
    found: number;
    saved: number;
    analyzed: number;
    relevant: number;
  } | null;
}

// Busqueda progresiva: acumula ofertas a medida que llegan por SSE.
export function useJobSearchStream(): LiveSearchState & {
  run: (
    q: string,
    pages: number,
    source?: string,
    location?: string,
    maxAgeDays?: number,
    append?: boolean,
  ) => Promise<LiveSearchState["summary"]>;
  cancel: () => void;
} {
  const [jobs, setJobs] = useState<StreamJobItem[]>([]);
  const [page, setPage] = useState(0);
  const [pages, setPages] = useState(1);
  const [found, setFound] = useState(0);
  const [analyzing, setAnalyzing] = useState(false);
  const [searching, setSearching] = useState(false);
  const [done, setDone] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [summary, setSummary] = useState<LiveSearchState["summary"]>(null);
  const closeRef = useRef<(() => void) | null>(null);
  const seenRef = useRef<Set<string>>(new Set());

  const cancel = useCallback(() => {
    closeRef.current?.();
    closeRef.current = null;
    setCancelled(true);
    setSearching(false);
    setAnalyzing(false);
  }, []);

  const run = useCallback(
    async (
      q: string,
      pages: number,
      source = "computrabajo",
      location?: string,
      maxAgeDays = 0,
      append = false,
    ) => {
      closeRef.current?.();
      if (!append) {
        seenRef.current.clear();
        setJobs([]);
        setFound(0);
      }
      setPage(0);
      setPages(pages);
      setAnalyzing(false);
      setSearching(true);
      setDone(false);
      setCancelled(false);
      setSearchError(null);
      setSummary(null);
      return await new Promise<LiveSearchState["summary"]>((resolve) => {
        const seen = seenRef.current;
        closeRef.current = streamSearchJobs(
          { q, pages, source, location, maxAgeDays },
          (event) => {
            if (event.type === "started") {
              setPages(event.pages);
            } else if (event.type === "jobs") {
              setPage(event.page);
              const fresh = event.jobs.filter((job) => {
                if (seen.has(job.id)) return false;
                seen.add(job.id);
                return true;
              });
              if (fresh.length > 0) {
                setJobs((prev) => [...prev, ...fresh]);
                setFound((count) => count + fresh.length);
              }
            } else if (event.type === "analyzing") {
              setAnalyzing(true);
            } else if (event.type === "done") {
              const summary = {
                query: event.query,
                source: event.source,
                found: event.found,
                saved: event.saved_unique,
                analyzed: event.analyzed,
                relevant: event.relevant,
              };
              setDone(true);
              setSearching(false);
              setAnalyzing(false);
              setSummary(summary);
              closeRef.current = null;
              resolve(summary);
            } else if (event.type === "error") {
              setSearchError(event.message || "Error en la búsqueda");
              setSearching(false);
              setAnalyzing(false);
              closeRef.current = null;
              resolve(null);
            } else if (event.type === "connection-error") {
              setSearchError(
                "Se perdió la conexión con el backend a mitad de la " +
                  "búsqueda. Lo ya guardado persiste: reintenta.",
              );
              setSearching(false);
              setAnalyzing(false);
              closeRef.current = null;
              resolve(null);
            }
          },
        );
      });
    },
    [],
  );

  useEffect(
    () => () => {
      closeRef.current?.();
    },
    [],
  );

  return {
    jobs,
    page,
    pages,
    found,
    analyzing,
    searching,
    done,
    cancelled,
    searchError,
    summary,
    run,
    cancel,
  };
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
