import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { DiscoverSummary } from "../services/jobs";
import type { SearchResult } from "../types/job";

interface SourceSummary {
  source: string;
  found: number;
  saved: number;
  error?: string;
}

interface SearchSession {
  query: string;
  source: string;
  pages: number;
  city: string;
  setQuery: (q: string) => void;
  setSource: (s: string) => void;
  setPages: (p: number) => void;
  setCity: (c: string) => void;
  // Ultimo resultado: sobrevive a la navegacion entre secciones, asi no
  // se re-ejecuta scraping al volver al Dashboard ni se pierde lo hallado.
  result: SearchResult | null;
  setResult: (r: SearchResult | null) => void;
  multi: SourceSummary[] | null;
  setMulti: (m: SourceSummary[] | null) => void;
  discovery: DiscoverSummary | null;
  setDiscovery: (d: DiscoverSummary | null) => void;
}

const SearchSessionContext = createContext<SearchSession | null>(null);

export function SearchSessionProvider({ children }: { children: ReactNode }) {
  const [query, setQuery] = useState("desarrollador python");
  const [source, setSource] = useState("all");
  const [pages, setPages] = useState(1);
  const [city, setCity] = useState("Bogotá");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [multi, setMulti] = useState<SourceSummary[] | null>(null);
  const [discovery, setDiscovery] = useState<DiscoverSummary | null>(null);

  const value = useMemo(
    () => ({
      query,
      source,
      pages,
      city,
      setQuery,
      setSource,
      setPages,
      setCity,
      result,
      setResult,
      multi,
      setMulti,
      discovery,
      setDiscovery,
    }),
    [query, source, pages, city, result, multi, discovery],
  );

  return (
    <SearchSessionContext.Provider value={value}>
      {children}
    </SearchSessionContext.Provider>
  );
}

export function useSearchSession(): SearchSession {
  const ctx = useContext(SearchSessionContext);
  if (!ctx) {
    throw new Error("useSearchSession fuera de SearchSessionProvider");
  }
  return ctx;
}
