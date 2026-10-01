import { useCallback, useEffect, useState } from "react";

export type Theme = "claro" | "oscuro" | "sistema";
const KEY = "ja-theme";

function systemDark(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

function resolve(t: Theme): "light" | "dark" {
  if (t === "claro") return "light";
  if (t === "oscuro") return "dark";
  return systemDark() ? "dark" : "light";
}

export function getStoredTheme(): Theme {
  const raw = window.localStorage.getItem(KEY);
  if (raw === "claro" || raw === "oscuro" || raw === "sistema") return raw;
  // Compatibilidad con el valor anterior "oscuro-sistema".
  if (raw === "oscuro-sistema") return "sistema";
  // Por defecto: tema oscuro en toda la pagina.
  return "oscuro";
}

export function applyTheme(t: Theme) {
  document.documentElement.dataset.theme =
    resolve(t) === "dark" ? "dark" : "light";
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => getStoredTheme());

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const current = window.localStorage.getItem(KEY);
      if (!current || current === "sistema" || current === "oscuro-sistema") {
        applyTheme("sistema");
      }
    };
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    window.localStorage.setItem(KEY, t);
    applyTheme(t);
  }, []);

  const toggle = useCallback(() => {
    const current = resolve(theme) === "dark" ? "claro" : "oscuro";
    setTheme(current);
  }, [theme, setTheme]);

  const isDark = resolve(theme) === "dark";
  return { theme, setTheme, toggle, isDark };
}
