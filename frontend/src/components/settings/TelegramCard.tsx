import { useEffect, useState } from "react";
import {
  fetchTelegramStatus,
  removeTelegramBot,
  saveTelegramBot,
  startTelegramLink,
  testTelegram,
  unlinkTelegram,
  type TelegramLinkStart,
  type TelegramStatus,
} from "../../services/telegram";

/** Telegram por usuario: bot propio (pegar key), conectar, probar. */
export function TelegramCard() {
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [link, setLink] = useState<TelegramLinkStart | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [manual, setManual] = useState<{ url: string; secret: string } | null>(
    null
  );

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

  const saveBot = async () => {
    if (!token.trim()) {
      setError("Pega primero el token de tu bot (BotFather).");
      return;
    }
    setBusy("bot");
    setError(null);
    setOk(null);
    setManual(null);
    try {
      const saved = await saveTelegramBot(token.trim());
      setToken("");
      await load();
      if (saved.webhook_ok) {
        setOk(`Bot @${saved.bot_username} configurado y webhook automático listo.`);
      } else {
        setOk(`Bot @${saved.bot_username} guardado. Falta registrar el webhook a mano:`);
        if (saved.manual_url && saved.manual_secret) {
          setManual({ url: saved.manual_url, secret: saved.manual_secret });
        }
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || "No se pudo guardar el bot.");
    } finally {
      setBusy(null);
    }
  };

  const removeBot = async () => {
    if (!confirm("¿Quitar tu bot? Se borrará su token y se desconectará el chat.")) return;
    setBusy("unbot");
    setError(null);
    setOk(null);
    setManual(null);
    try {
      await removeTelegramBot();
      setLink(null);
      await load();
      setOk("Bot eliminado.");
    } catch (e: any) {
      setError(e.response?.data?.detail || "No se pudo quitar el bot.");
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
      {/* Bot propio: cada persona pega su key de BotFather */}
      <div style={{ marginBottom: 12, fontSize: 13 }}>
        <p style={{ margin: "0 0 6px" }}>
          <strong>Tu bot</strong>{" "}
          <span className="card-sub">
            (créalo con @BotFather y pega aquí su token; la app lo valida,
            lo cifra y configura todo sola)
          </span>
        </p>
        {status?.has_bot ? (
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <span>
              Bot configurado:{" "}
              <strong>
                @{status.bot_username ?? "?"}
              </strong>
            </span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={busy === "unbot"}
              onClick={() => void removeBot()}
            >
              {busy === "unbot" ? "Quitando…" : "Quitar bot"}
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              type={showToken ? "text" : "password"}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="123456789:AAH… (token de BotFather)"
              autoComplete="off"
              spellCheck={false}
              style={{ flex: "1 1 220px", minWidth: 0 }}
            />
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setShowToken((v) => !v)}
            >
              {showToken ? "Ocultar" : "Ver"}
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy === "bot"}
              onClick={() => void saveBot()}
            >
              {busy === "bot" ? "Guardando…" : "Guardar bot"}
            </button>
          </div>
        )}
        {manual && (
          <div style={{ marginTop: 8 }}>
            <p className="card-sub" style={{ margin: "0 0 4px" }}>
              El servidor no tiene URL pública: registra el webhook a mano
              abriendo esta dirección (reemplaza{" "}
              <code>&lt;TU_TOKEN&gt;</code> por tu token) con el secret de
              abajo como <code>secret_token</code>:
            </p>
            <code style={{ display: "block", wordBreak: "break-all", marginBottom: 4 }}>
              {manual.url}
            </code>
            <code style={{ display: "block", wordBreak: "break-all" }}>
              secret: {manual.secret}
            </code>
          </div>
        )}
      </div>
      {!status ? (
        <p className="card-sub">Cargando estado…</p>
      ) : !status.connected ? (
        <div>
          <p style={{ fontSize: 13, margin: "0 0 8px" }}>
            Estado: <strong>No conectado</strong>
          </p>
          {!link ? (
            status.has_bot ? (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={busy === "link"}
                onClick={() => void connect()}
              >
                {busy === "link" ? "Generando…" : "Conectar Telegram"}
              </button>
            ) : (
              <p className="card-sub" style={{ margin: 0 }}>
                Guarda primero tu bot arriba para poder conectar tu chat.
              </p>
            )
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
