import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  Briefcase,
  LogIn,
  Phone,
  User as UserIcon,
  UserPlus,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { isFirebaseConfigured } from "../lib/firebase";
import type { AuthApiError } from "../services/auth";

type Mode = "register" | "login";

export function Login() {
  const {
    configured,
    googlePopup,
    establishSession,
    registerWithGoogle,
    loginWithGoogleStrict,
    completeProfile,
    loginAsGuest,
    logout,
    firebaseUser,
    profile,
    needsProfile,
  } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const guestAuto = useRef(false);
  // Sin elección no hay botón de Google: primero Registrarse o Login,
  // y dentro de cada uno su opción con Google.
  const [mode, setMode] = useState<Mode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [nombre, setNombre] = useState("");
  const [telefono, setTelefono] = useState("");
  const [touchedNombre, setTouchedNombre] = useState(false);
  const [touchedTelefono, setTouchedTelefono] = useState(false);

  const uid = firebaseUser?.uid ?? null;
  // Al cambiar de cuenta se resetea lo editado.
  useEffect(() => {
    setTouchedNombre(false);
    setTouchedTelefono(false);
  }, [uid]);
  // Pre-rellena desde Google/backend sin pisar lo que ya escribio.
  useEffect(() => {
    if (!touchedNombre) {
      setNombre(profile?.nombre || firebaseUser?.displayName || "");
    }
    if (!touchedTelefono) {
      setTelefono(profile?.telefono || "");
    }
  }, [firebaseUser, profile, touchedNombre, touchedTelefono]);

  const googleName = firebaseUser?.displayName ?? "";
  const googleEmail = firebaseUser?.email ?? profile?.email ?? "";

  // Si ya hay sesion completa, no quedarse en /login.
  useEffect(() => {
    if (firebaseUser && !needsProfile) {
      navigate("/dashboard", { replace: true });
    }
  }, [firebaseUser, needsProfile, navigate]);

  // Atajo demo: /login?guest=1 entra como invitado sin clic extra.
  useEffect(() => {
    if (guestAuto.current || searchParams.get("guest") !== "1") return;
    if (firebaseUser) return;
    guestAuto.current = true;
    void (async () => {
      setBusy(true);
      try {
        await loginAsGuest();
        navigate("/dashboard", { replace: true });
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "No se pudo entrar como invitado.",
        );
      } finally {
        setBusy(false);
      }
    })();
  }, [searchParams, firebaseUser, loginAsGuest, navigate]);

  const switchMode = (m: Mode) => {
    setMode(m);
    setError(null);
    setInfo(null);
  };

  // Paso 1 (registro): popup Google. Si la cuenta ya esta completa,
  // no se registra de nuevo: se le manda al login.
  const doRegisterGoogle = async () => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const fb = await googlePopup();
      const me = await establishSession(fb);
      if (me?.is_profile_complete) {
        await logout();
        setMode("login");
        setError("ya existe esta cuenta ingresa por login");
      }
      // Si no, se queda aquí y aparece el formulario (paso 2).
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "No se pudo conectar con Google.",
      );
    } finally {
      setBusy(false);
    }
  };

  // Paso 2 (registro): nombre + telefono UNA sola vez. Si otro
  // dispositivo ya la registro, 409 y se le manda al login.
  const doRegisterSubmit = async () => {
    if (!nombre.trim()) {
      setError("El nombre es obligatorio.");
      return;
    }
    if (!telefono.trim()) {
      setError("El teléfono es obligatorio (se pide una sola vez).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await registerWithGoogle(nombre.trim(), telefono.trim());
      navigate("/dashboard", { replace: true });
    } catch (e) {
      const code = (e as AuthApiError)?.code;
      if (code === "ACCOUNT_EXISTS") {
        await logout();
        setMode("login");
        setError("ya existe esta cuenta ingresa por login");
      } else {
        setError(e instanceof Error ? e.message : "No se pudo registrar.");
      }
    } finally {
      setBusy(false);
    }
  };

  // Entrada: popup Google + chequeo estricto en backend.
  const doLoginGoogle = async () => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const fb = await googlePopup();
      await establishSession(fb);
      await loginWithGoogleStrict();
      // Si entra: el redirect lleva al dashboard (o al formulario
      // legacy si es una cuenta vieja sin telefono).
    } catch (e) {
      const code = (e as AuthApiError)?.code;
      if (code === "NOT_REGISTERED") {
        await logout();
        setMode("register");
        setError("tienes que registrarte");
      } else {
        setError(
          e instanceof Error ? e.message : "No se pudo iniciar sesión.",
        );
      }
    } finally {
      setBusy(false);
    }
  };

  // Cuentas legacy (existen pero sin telefono): se completa una vez.
  const doLoginComplete = async () => {
    if (!telefono.trim()) {
      setError("El teléfono es obligatorio.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await completeProfile(
        nombre.trim() || googleName || "Usuario",
        telefono.trim(),
      );
      navigate("/dashboard", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setBusy(false);
    }
  };

  const doGuest = async () => {
    setBusy(true);
    setError(null);
    try {
      await loginAsGuest();
      navigate("/dashboard", { replace: true });
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "No se pudo entrar como invitado.",
      );
    } finally {
      setBusy(false);
    }
  };

  // Paso 2: formulario tras el popup (registro nuevo o legacy sin telefono).
  // Solo nombre + telefono; el gmail viene de Google y se guarda una vez.
  if (firebaseUser && !firebaseUser.isAnonymous && needsProfile) {
    const isRegister = mode !== "login";
    return (
      <div className="auth-wrap">
        <div className="auth-card">
          <h1>
            <Briefcase size={19} />{" "}
            {isRegister ? "Completa tu registro" : "Un dato pendiente"}
          </h1>
          <p className="card-sub">
            {isRegister
              ? "Ya entraste con Google. Solo guardamos tu nombre, teléfono y gmail (una sola vez)."
              : "Tu cuenta existe pero le falta el teléfono. Lo guardamos una sola vez."}
          </p>
          {error && <div className="alert-error">{error}</div>}
          <div className="field">
            <label>Nombre</label>
            <div className="auth-input-icon">
              <UserIcon size={14} />
              <input
                className="input"
                value={nombre || googleName}
                onChange={(e) => {
                  setTouchedNombre(true);
                  setNombre(e.target.value);
                }}
                placeholder="Tu nombre"
              />
            </div>
          </div>
          <div className="field">
            <label>Gmail (de tu cuenta Google)</label>
            <input className="input" value={googleEmail} disabled />
          </div>
          <div className="field">
            <label>Teléfono</label>
            <div className="auth-input-icon">
              <Phone size={14} />
              <input
                className="input"
                value={telefono}
                onChange={(e) => {
                  setTouchedTelefono(true);
                  setTelefono(e.target.value);
                }}
                placeholder="+57 300 123 4567"
                inputMode="tel"
              />
            </div>
          </div>
          <button
            className="btn btn-primary auth-btn"
            disabled={busy}
            onClick={isRegister ? doRegisterSubmit : doLoginComplete}
          >
            {busy ? "Guardando…" : "Guardar y entrar"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h1>
          <Briefcase size={19} /> Job Agent
        </h1>
        <div style={{ display: "flex", gap: 8, margin: "12px 0" }}>
          <button
            type="button"
            className={`btn btn-sm ${mode === "register" ? "btn-primary" : "btn-ghost"}`}
            onClick={() => switchMode("register")}
          >
            <UserPlus size={14} /> Registrarse
          </button>
          <button
            type="button"
            className={`btn btn-sm ${mode === "login" ? "btn-primary" : "btn-ghost"}`}
            onClick={() => switchMode("login")}
          >
            <LogIn size={14} /> Login
          </button>
        </div>
        {mode === null && (
          <p className="card-sub">
            Elige una opción para continuar con tu cuenta de Google.
          </p>
        )}
        {mode === "register" && (
          <>
            <p className="card-sub">
              Crea tu cuenta con Google: el teléfono se pide una sola vez y
              queda guardado.
            </p>
            <button
              className="btn btn-primary auth-btn"
              disabled={busy || !isFirebaseConfigured}
              onClick={doRegisterGoogle}
            >
              <UserPlus size={15} />{" "}
              {busy ? "Conectando…" : "Registrarme con Google"}
            </button>
          </>
        )}
        {mode === "login" && (
          <>
            <p className="card-sub">
              Entra con tu cuenta Google ya registrada. Sin registro no hay
              entrada.
            </p>
            <button
              className="btn btn-primary auth-btn"
              disabled={busy || !isFirebaseConfigured}
              onClick={doLoginGoogle}
            >
              <LogIn size={15} />{" "}
              {busy ? "Conectando…" : "Login con Google"}
            </button>
          </>
        )}
        {!isFirebaseConfigured && (
          <div className="notice-pending">
            Falta configurar Firebase en el frontend (VITE_FIREBASE_* en
            frontend/.env). Sigue la guia de activacion de Google en Firebase.
          </div>
        )}
        {error && <div className="alert-error">{error}</div>}
        {info && <div className="alert-success">{info}</div>}
        <button
          className="btn btn-ghost auth-btn"
          disabled={busy || !isFirebaseConfigured}
          onClick={doGuest}
          title="Sesión anónima para probar sin cuenta de Google"
        >
          <UserIcon size={15} /> {busy ? "Entrando…" : "Entrar como invitado"}
        </button>
        {!configured && (
          <p className="auth-hint">
            <Link to="/dashboard">Continuar sin iniciar sesión (modo local)</Link>
          </p>
        )}
        <p className="auth-hint">
          Al continuar aceptas guardar nombre, telefono y gmail para tu cuenta.
        </p>
      </div>
    </div>
  );
}
