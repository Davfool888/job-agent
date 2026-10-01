import { initializeApp, type FirebaseApp } from "firebase/app";
import {
  browserLocalPersistence,
  getAuth,
  GoogleAuthProvider,
  setPersistence,
  type Auth,
} from "firebase/auth";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY ?? "",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN ?? "",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID ?? "",
  appId: import.meta.env.VITE_FIREBASE_APP_ID ?? "",
};

export const isFirebaseConfigured = Boolean(
  config.apiKey && config.authDomain && config.projectId && config.appId,
);

let app: FirebaseApp | null = null;
let auth: Auth | null = null;
let persistenceReady: Promise<void> | null = null;

if (isFirebaseConfigured) {
  app = initializeApp(config);
  auth = getAuth(app);
  // Sesion persistente en el navegador: no pide login en cada visita.
  persistenceReady = setPersistence(auth, browserLocalPersistence).catch(() => {});
}

export function getFirebaseAuth(): Auth {
  if (!auth) {
    throw new Error(
      "Firebase no configurado. Define VITE_FIREBASE_API_KEY, VITE_FIREBASE_AUTH_DOMAIN, VITE_FIREBASE_PROJECT_ID y VITE_FIREBASE_APP_ID en frontend/.env",
    );
  }
  return auth;
}

export async function ensureAuthReady(): Promise<void> {
  if (persistenceReady) await persistenceReady;
}

export const googleProvider = new GoogleAuthProvider();
// Solo pide lo basico: nombre + email de Google.
googleProvider.addScope("profile");
googleProvider.addScope("email");
googleProvider.setCustomParameters({ prompt: "select_account" });

// Cuenta administradora: la unica que ve el perfil base global.
// Cualquier otra sesion solo ve scope own/demo; con scope compartido
// (backend sin verificacion) el frontend no muestra nada.
export const ADMIN_EMAIL = (
  import.meta.env.VITE_ADMIN_EMAIL ?? "davfool888@gmail.com"
).toLowerCase();
