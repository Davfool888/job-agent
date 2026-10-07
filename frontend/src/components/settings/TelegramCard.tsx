import { useEffect, useState } from "react";
import {
  fetchTelegramStatus,
  startTelegramLink,
  testTelegram,
  unlinkTelegram,
  type TelegramLinkStart,
  type TelegramStatus,
} from "../../services/telegram";

/** Telegram por usuario: conectar (deep link), estado, probar, desconectar. */
export function TelegramCard() {
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [link, setLink] = useState<TelegramLinkStart | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const load = async () => {
    try {
      setStatus(await fetchTelegramStatus());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error cargando estado");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const connect = async () => {
    setBusy("link");
    setError(null);
    setOk(null);
    try {
      setLink(await startTelegramLink());
    } catch (e: any) {
      setError(e.response?.data?.detail || "No se pudo iniciar la vinculación.");
    } finally {
      setBusy(null);
    }
  };

  const verify = async () => {
    setBusy("verify");
    setError(null);
    try {
      await load();
      setOk("Estado actualizado.");
    } finally {
      setBusy(null);
    }
  };

  const test = async () => {
    setBusy("test");
    setError(null);
    setOk(null);
    try {
      await testTelegram();
      setOk("Revisa tu Telegram: debió llegarte un mensaje de prueba.");
    } catch (e: any) {
      setError(e.response?.data?.detail || "No se pudo enviar la prueba.");
    } finally {
      setBusy(null);
    }
  };

  const disconnect = async () => {
    if (!confirm("¿Desconectar Telegram? Dejarás de recibir ofertas ahí.")) return;
    setBusy("unlink");
    setError(null);
    setOk(null);
    try {
      await unlinkTelegram();
      setLink(null);
      await load();
      setOk("Telegram desconectado.");
    } catch (e: any) {
      setError(e.response?.data?.detail || "No se pudo desconectar.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 className="card-title">Telegram</h3>
      <p className="card-sub">
        Recibe aquí las nuevas ofertas de tus búsquedas, con botón para
        abrir la vacante original.
      </p>
      {error && (
        <p style={{ color: "var(--danger)", fontSize: 13 }}>⚠ {error}</p>
      )}
      {ok && (
        <p style={{ color: "var(--success)", fontSize: 13 }}>✅ {ok}</p>
      )}
      {!status ? (
        <p className="card-sub">Cargando estado…</p>
      ) : !status.connected ? (
        <div>
          <p style={{ fontSize: 13, margin: "0 0 8px" }}>
            Estado: <strong>No conectado</strong>
          </p>
          {!link ? (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy === "link"}
              onClick={() => void connect()}
            >
              {busy === "link" ? "Generando…" : "Conectar Telegram"}
            </button>
          ) : (
            <div style={{ fontSize: 13 }}>
              <p style={{ margin: "0 0 8px" }}>
                1. Abre el bot con este enlace (o busca{" "}
                <strong>@{link.bot_username}</strong> y pulsa{" "}
                <strong>Iniciar</strong>):
              </p>
              <p style={{ margin: "0 0 8px" }}>
                <a
                  className="btn btn-primary btn-sm"
                  href={link.deep_link}
                  target="_blank"
                  rel="noreferrer"
                >
                  Abrir bot en Telegram
                </a>{" "}
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    void navigator.clipboard?.writeText(link.deep_link);
                    setOk("Enlace copiado.");
                  }}
                >
                  Copiar enlace
                </button>
              </p>
              <p className="card-sub" style={{ margin: "0 0 8px" }}>
                2. El código vence en {link.expires_in_minutes} minutos y
                es de un solo uso (queda atado a tu cuenta).
              </p>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={busy === "verify"}
                onClick={() => void verify()}
              >
                {busy === "verify" ? "Verificando…" : "Ya lo hice, verificar"}
              </button>
            </div>
          )}
        </div>
      ) : (
        <div style={{ fontSize: 13 }}>
          <p style={{ margin: "0 0 8px" }}>
            Estado: <strong>Telegram conectado ✓</strong>
            {status.username ? (
              <>
                {" "}(@{status.username})
              </>
            ) : null}
            {!status.valid && (
              <span style={{ color: "var(--danger)" }}>
                {" "}
                — sin respuesta del chat (¿bloqueaste al bot?)
              </span>
            )}
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={busy === "test"}
              onClick={() => void test()}
            >
              {busy === "test" ? "Enviando…" : "Probar conexión"}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={busy === "unlink"}
              onClick={() => void disconnect()}
            >
              Desconectar Telegram
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
