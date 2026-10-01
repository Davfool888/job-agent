import { useState } from "react";
import { Header } from "../components/layout/Header";
import { API_URL } from "../services/api";
import { checkHealth } from "../services/jobs";
import { useTheme, type Theme } from "../hooks/useTheme";

export function Settings() {
  const { theme, setTheme } = useTheme();
  const [health, setHealth] = useState<string>("Sin comprobar");
  const [checking, setChecking] = useState(false);

  const ping = async () => {
    setChecking(true);
    const ok = await checkHealth();
    setHealth(ok ? "Backend responde OK" : "Backend no responde");
    setChecking(false);
  };

  return (
    <>
      <Header title="Configuración" subtitle="Conexión y preferencias visuales" />
      <div className="content">
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 className="card-title">Backend</h3>
          <p className="card-sub">
            La URL vive en <code>frontend/.env</code> como{" "}
            <code>VITE_API_URL</code> (actual: {API_URL}).
          </p>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <button className="btn btn-ghost btn-sm" onClick={ping} disabled={checking}>
              {checking ? "Comprobando…" : "Probar conexión"}
            </button>
            <span style={{ fontSize: 13 }}>{health}</span>
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">Apariencia</h3>
          <p className="card-sub">
            Solo preferencia visual guardada en este navegador.
          </p>
          <div className="field" style={{ maxWidth: 260 }}>
            <label>Tema</label>
            <select
              className="select"
              value={theme}
              onChange={(e) => setTheme(e.target.value as Theme)}
            >
              <option value="oscuro">Oscuro</option>
              <option value="claro">Claro</option>
              <option value="sistema">Seguir al sistema</option>
            </select>
          </div>
        </div>
      </div>
    </>
  );
}
