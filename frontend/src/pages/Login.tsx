import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Briefcase, LogIn, Phone, User as UserIcon } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { isFirebaseConfigured } from "../lib/firebase";

export function Login() {
  const {
    configured,
    loginWithGoogle,
    completeProfile,
    firebaseUser,
    profile,
    needsProfile,
  } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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

  const doLogin = async () => {
    setBusy(true);
    setError(null);
    try {
      await loginWithGoogle();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "No se pudo iniciar sesion con Google.",
      );
    } finally {
      setBusy(false);
    }
  };

  const doComplete = async () => {
    if (!nombre.trim()) {
      setError("El nombre es obligatorio.");
      return;
    }
    if (!telefono.trim()) {
      setError("El telefono es obligatorio.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await completeProfile(nombre.trim(), telefono.trim());
      navigate("/dashboard", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setBusy(false);
    }
  };

  // Paso 2: completar registro (solo nombre + telefono; gmail viene de Google).
  if (firebaseUser && needsProfile) {
    return (
      <div className="auth-wrap">
        <div className="auth-card">
          <h1>
            <Briefcase size={19} /> Completa tu registro
          </h1>
          <p className="card-sub">
            Ya entraste con Google. Solo guardamos tu nombre, telefono y gmail.
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
            <label>Telefono</label>
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
            onClick={doComplete}
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
        <p className="card-sub">
          Inicia sesion o registrate con tu cuenta de Google. La sesion queda
          activa en este navegador.
        </p>
        {!isFirebaseConfigured && (
          <div className="notice-pending">
            Falta configurar Firebase en el frontend (VITE_FIREBASE_* en
            frontend/.env). Sigue la guia de activacion de Google en Firebase.
          </div>
        )}
        {error && <div className="alert-error">{error}</div>}
        <button
          className="btn btn-primary auth-btn"
          disabled={busy || !isFirebaseConfigured}
          onClick={doLogin}
        >
          <LogIn size={15} /> {busy ? "Conectando…" : "Continuar con Google"}
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
