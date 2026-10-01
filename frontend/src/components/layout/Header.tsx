import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { checkHealth } from "../../services/jobs";
import { useTheme } from "../../hooks/useTheme";

interface Props {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export function Header({ title, subtitle, actions }: Props) {
  const [online, setOnline] = useState<boolean | null>(null);
  const { toggle, isDark } = useTheme();

  useEffect(() => {
    let alive = true;
    checkHealth().then((ok) => alive && setOnline(ok));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <header className="header">
      <div>
        <h2>{title}</h2>
        {subtitle && <p className="header-sub">{subtitle}</p>}
      </div>
      <div className="header-spacer" />
      {actions}
      <button
        className="btn btn-ghost btn-sm"
        onClick={toggle}
        title={isDark ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
        aria-label="Cambiar tema"
      >
        {isDark ? <Sun size={14} /> : <Moon size={14} />}
      </button>
      <span className="backend-pill" title="Estado del backend FastAPI">
        <span
          className={`health-dot ${online ? "health-ok" : "health-bad"}`}
        />
        {online === null ? "Backend…" : online ? "Backend OK" : "Backend caído"}
      </span>
    </header>
  );
}
