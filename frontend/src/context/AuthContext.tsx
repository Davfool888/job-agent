import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  onAuthStateChanged,
  signInAnonymously,
  signInWithPopup,
  signOut,
  type User as FirebaseUser,
} from "firebase/auth";
import {
  ensureAuthReady,
  getFirebaseAuth,
  googleProvider,
  isFirebaseConfigured,
} from "../lib/firebase";
import {
  fetchMe,
  loginAccount,
  registerAccount,
  updateMe,
  type AuthApiError,
  type BackendUser,
} from "../services/auth";

export type { AuthApiError };

interface AuthState {
  configured: boolean;
  initializing: boolean;
  firebaseUser: FirebaseUser | null;
  profile: BackendUser | null;
  needsProfile: boolean;
  isGuest: boolean;
  authError: string | null;
  loginWithGoogle: () => Promise<void>;
  loginAsGuest: () => Promise<void>;
  switchAccount: () => Promise<void>;
  completeProfile: (nombre: string, telefono: string) => Promise<void>;
  googlePopup: () => Promise<FirebaseUser>;
  establishSession: (fb: FirebaseUser) => Promise<BackendUser | null>;
  registerWithGoogle: (nombre: string, telefono: string) => Promise<BackendUser>;
  loginWithGoogleStrict: () => Promise<BackendUser>;
  refreshProfile: () => Promise<void>;
  logout: () => Promise<void>;
}

function profileCacheKey(uid: string): string {
  return `jobagent_profile_${uid}`;
}

function readCachedProfile(uid: string): BackendUser | null {
  try {
    const raw = window.localStorage.getItem(profileCacheKey(uid));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BackendUser;
    if (parsed && parsed.uid === uid) return parsed;
  } catch {
    /* cache ilegible */
  }
  return null;
}

function writeCachedProfile(user: BackendUser): void {
  try {
    window.localStorage.setItem(
      profileCacheKey(user.uid),
      JSON.stringify(user),
    );
  } catch {
    /* almacenamiento lleno/bloqueado */
  }
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [initializing, setInitializing] = useState(true);
  const [firebaseUser, setFirebaseUser] = useState<FirebaseUser | null>(null);
  const [profile, setProfile] = useState<BackendUser | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  const syncProfile = useCallback(async (fb: FirebaseUser | null) => {
    if (!fb) {
      setProfile(null);
      return null;
    }
    try {
      const token = await fb.getIdToken();
      const me = await fetchMe(token);
      // Cache local: si el backend cae luego, la sesion sigue completa.
      writeCachedProfile(me);
      // Prefill nombre desde Google si el backend aun no lo tiene.
      if (!me.nombre?.trim() && fb.displayName) {
        const prefilled = { ...me, nombre: fb.displayName };
        setProfile(prefilled);
        return prefilled;
      }
      setProfile(me);
      return me;
    } catch (e) {
      // Backend sin Firebase Admin o sin red: reutiliza lo ultimo
      // guardado para NO volver a pedir telefono cada vez.
      const cached = readCachedProfile(fb.uid);
      if (
        cached &&
        cached.nombre?.trim() &&
        cached.telefono?.trim()
      ) {
        setProfile({ ...cached, is_profile_complete: true });
        setAuthError(null);
        return cached;
      }
      // Sin nada guardado: datos de Google, incompleto.
      setProfile({
        uid: fb.uid,
        email: fb.email ?? "",
        nombre: fb.displayName ?? "",
        telefono: "",
        is_profile_complete: false,
      });
      setAuthError(
        e instanceof Error ? e.message : "No se pudo cargar el perfil.",
      );
      return null;
    }
  }, []);

  useEffect(() => {
    if (!isFirebaseConfigured) {
      setInitializing(false);
      return;
    }
    let alive = true;
    (async () => {
      await ensureAuthReady();
      const auth = getFirebaseAuth();
      const unsub = onAuthStateChanged(auth, async (fb) => {
        if (!alive) return;
        setFirebaseUser(fb);
        setAuthError(null);
        await syncProfile(fb);
        if (alive) setInitializing(false);
      });
      return unsub;
    })().catch(() => alive && setInitializing(false));
    return () => {
      alive = false;
    };
  }, [syncProfile]);

  const loginWithGoogle = useCallback(async () => {
    setAuthError(null);
    const auth = getFirebaseAuth();
    const cred = await signInWithPopup(auth, googleProvider);
    setFirebaseUser(cred.user);
    await syncProfile(cred.user);
  }, [syncProfile]);

  // Cambiar de cuenta sin cerrar primero: el popup muestra el selector
  // de cuentas de Google (prompt=select_account); si cancela, la sesion
  // actual se conserva.
  const switchAccount = useCallback(async () => {
    await loginWithGoogle();
  }, [loginWithGoogle]);

  // Invitado: sesion anonima de Firebase (sin Google, sin telefono).
  // Persiste igual en este navegador. Requiere el proveedor Anonymous
  // activo en Firebase Console → Authentication → Sign-in method.
  const loginAsGuest = useCallback(async () => {
    setAuthError(null);
    const auth = getFirebaseAuth();
    try {
      const cred = await signInAnonymously(auth);
      setFirebaseUser(cred.user);
      await syncProfile(cred.user);
    } catch (e) {
      const code = (e as { code?: string })?.code ?? "";
      if (
        code === "auth/operation-not-allowed" ||
        code === "auth/admin-restricted-operation"
      ) {
        throw new Error(
          "Activa el proveedor 'Anonymous' en Firebase Console → " +
            "Authentication → Sign-in method.",
        );
      }
      throw e;
    }
  }, [syncProfile]);

  const completeProfile = useCallback(
    async (nombre: string, telefono: string) => {
      if (!firebaseUser) throw new Error("Sin sesion.");
      const token = await firebaseUser.getIdToken();
      try {
        const me = await updateMe(token, { nombre, telefono });
        writeCachedProfile(me);
        setProfile(me);
      } catch {
        // Sin backend: guarda local para no bloquear el registro.
        const fallback: BackendUser = {
          uid: firebaseUser.uid,
          email: firebaseUser.email ?? "",
          nombre,
          telefono,
          is_profile_complete: true,
        };
        writeCachedProfile(fallback);
        setProfile(fallback);
      }
    },
    [firebaseUser],
  );

  // Popup Google crudo (los flujos registro/login deciden despues).
  const googlePopup = useCallback(async () => {
    setAuthError(null);
    const auth = getFirebaseAuth();
    const cred = await signInWithPopup(auth, googleProvider);
    setFirebaseUser(cred.user);
    return cred.user;
  }, []);

  const establishSession = useCallback(
    async (fb: FirebaseUser) => {
      setFirebaseUser(fb);
      setAuthError(null);
      return syncProfile(fb);
    },
    [syncProfile],
  );

  // Registro estricto: 409 si la cuenta ya existe (no pisa).
  const registerWithGoogle = useCallback(
    async (nombre: string, telefono: string) => {
      if (!firebaseUser) throw new Error("Sin sesion.");
      const token = await firebaseUser.getIdToken();
      const me = await registerAccount(token, { nombre, telefono });
      writeCachedProfile(me);
      setProfile(me);
      return me;
    },
    [firebaseUser],
  );

  // Entrada estricta: 404 si no hay registro previo.
  const loginWithGoogleStrict = useCallback(async () => {
    if (!firebaseUser) throw new Error("Sin sesion.");
    const token = await firebaseUser.getIdToken();
    const me = await loginAccount(token);
    writeCachedProfile(me);
    setProfile(me);
    return me;
  }, [firebaseUser]);

  const refreshProfile = useCallback(async () => {
    if (firebaseUser) await syncProfile(firebaseUser);
  }, [firebaseUser, syncProfile]);

  const logout = useCallback(async () => {
    const auth = getFirebaseAuth();
    await signOut(auth);
    setFirebaseUser(null);
    setProfile(null);
  }, []);

  const needsProfile = useMemo(() => {
    if (!firebaseUser) return false;
    // El invitado entra directo: sin nombre ni telefono obligatorios.
    if (firebaseUser.isAnonymous) return false;
    if (!profile) return true;
    return !profile.is_profile_complete;
  }, [firebaseUser, profile]);

  const value: AuthState = {
    configured: isFirebaseConfigured,
    initializing,
    firebaseUser,
    profile,
    needsProfile,
    isGuest: firebaseUser?.isAnonymous ?? false,
    authError,
    loginWithGoogle,
    loginAsGuest,
    switchAccount,
    completeProfile,
    googlePopup,
    establishSession,
    registerWithGoogle,
    loginWithGoogleStrict,
    refreshProfile,
    logout,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth fuera de AuthProvider");
  return ctx;
}
