// Hook DEDICADO a la busqueda progresiva del Dashboard.
//
// Aislamiento: vive en su propio archivo para que cambios en otros hooks
// de useApi.ts (useJobs, useStats, perfiles, etc.) no le afecten. La unica
// interconexion es el servicio ../services/searchStream (SSE + fallback
// REST) y los tipos ../types/job. Misma API publica que antes para no
// romper el Dashboard.

import { useCallback, useEffect, useRef, useState } from "react";
import { openSearchStream } from "../services/searchStream";
import type { StreamJobItem } from "../types/job";

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
        closeRef.current = openSearchStream(
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
