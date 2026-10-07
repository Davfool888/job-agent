import { useEffect, useState } from "react";
import {
  aiStatusLabel,
  deleteAiKey,
  fetchAiStatus,
  saveAiKey,
  type AiKeyStatus,
} from "../../services/aiKeys";

function badgeColor(status: string): string {
  if (status === "disponible") return "var(--success)";
  if (status === "cuota_agotada") return "var(--text-muted)";
  return "var(--danger)";
}

/** Keys propias por proveedor (cuota del usuario, nunca global).
 * Jamas muestra valores de keys: solo estado + guardar/borrar.
 */
export function AiKeysCard() {
  const [rows, setRows] = useState<AiKeyStatus[] | null>(null);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const load = async () => {
    try {
      setRows(await fetchAiStatus());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error cargando estado");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const save = async (provider: string) => {
    const key = (inputs[provider] ?? "").trim();
    if (!key) {
      setError("Pega primero la API key.");
      return;
    }
    setBusy(provider);
    setError(null);
    setOk(null);
    try {
      await saveAiKey(provider, key);
      setInputs((m) => ({ ...m, [provider]: "" }));
      await load();
      setOk("Key guardada y verificada.");
    } catch (e: any) {
      setError(e.response?.data?.detail || "No se pudo guardar la key.");
    } finally {
      setBusy(null);
    }
  };

  const remove = async (provider: string) => {
    if (!confirm("¿Borrar esta API key?")) return;
    setBusy(provider);
    setError(null);
    setOk(null);
    try {
      await deleteAiKey(provider);
      await load();
      setOk("Key eliminada.");
    } catch (e: any) {
      setError(e.response?.data?.detail || "No se pudo borrar.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 className="card-title">APIs de IA</h3>
      <p className="card-sub">
        Registra tus propias keys para adaptar el CV con tu cuota (nunca
        se usa la del proyecto). Solo se guarda el estado, jamás el valor
        de la key. Sin keys configuradas, la generación usa el modo
        determinístico local.
      </p>
      {error && (
        <p style={{ color: "var(--danger)", fontSize: 13 }}>⚠ {error}</p>
      )}
      {ok && (
        <p style={{ color: "var(--success)", fontSize: 13 }}>✅ {ok}</p>
      )}
      {!rows ? (
        <p className="card-sub">Cargando proveedores…</p>
      ) : (
        rows.map((r) => (
          <div
            key={r.id}
            style={{
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 10,
              marginBottom: 8,
              opacity:
                r.configured && r.status !== "disponible" ? 0.75 : 1,
            }}
          >
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <strong>{r.label}</strong>
              <span className="card-sub">· {r.model}</span>
              <span style={{ color: badgeColor(r.status), fontSize: 12.5 }}>
                ● {r.configured ? aiStatusLabel(r.status) : "sin configurar"}
              </span>
              {r.configured && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ marginLeft: "auto" }}
                  disabled={busy === r.id}
                  onClick={() => void remove(r.id)}
                >
                  Borrar key
                </button>
              )}
            </div>
            <p className="card-sub" style={{ margin: "6px 0" }}>
              {r.key_help}
              {r.configured && r.detail ? ` — ${r.detail}` : ""}
            </p>
            <div style={{ display: "flex", gap: 6 }}>
              <input
                className="input"
                type="password"
                style={{ flex: 1 }}
                value={inputs[r.id] ?? ""}
                disabled={busy === r.id}
                onChange={(e) =>
                  setInputs((m) => ({ ...m, [r.id]: e.target.value }))
                }
                placeholder={
                  r.configured
                    ? "Pegar nueva key para reemplazar…"
                    : "Pegar API key…"
                }
                autoComplete="off"
              />
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={busy === r.id}
                onClick={() => void save(r.id)}
              >
                {busy === r.id ? "Verificando…" : "Guardar"}
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
