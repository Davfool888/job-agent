import { useEffect, useRef, useState } from "react";

// Ventana de renderizado: pinta las primeras `pageSize` y amplía al
// bajar (IntersectionObserver). Los filtros/cambios de cantidad
// reinician a la primera ventana. Puro cliente: no pide al backend.
export function usePagedList<T>(items: T[], pageSize = 20) {
  const [count, setCount] = useState(pageSize);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setCount(pageSize);
  }, [items.length, pageSize]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setCount((c) => c + pageSize);
        }
      },
      { rootMargin: "500px" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [pageSize, items.length]);

  const visible = items.slice(0, count);
  return {
    visible,
    sentinelRef,
    hasMore: items.length > visible.length,
    shown: visible.length,
    total: items.length,
  };
}
