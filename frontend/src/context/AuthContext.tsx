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
import { fetchMe, updateMe, type BackendUser } from "../services/auth";

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
  refreshProfile: () => Promise<void>;
  logout: () => Promise<void>;
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
      return;
    }
    try {
      const token = await fb.getIdToken();
      const me = await fetchMe(token);
      // Prefill nombre desde Google si el backend aun no lo tiene.
      if (!me.nombre?.trim() && fb.displayName) {
        setProfile({ ...me, nombre: fb.displayName });
      } else {
        setProfile(me);
      }
    } catch (e) {
      // Backend sin Firebase Admin o sin red: usa datos de Google.
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
        window.localStorage.setItem(
          `jobagent_profile_${firebaseUser.uid}`,
          JSON.stringify(fallback),
        );
        setProfile(fallback);
      }
    },
    [firebaseUser],
  );

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
