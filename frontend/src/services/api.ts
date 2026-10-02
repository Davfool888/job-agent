import axios from "axios";
import { getAuth } from "firebase/auth";

// La URL del backend SOLO vive aqui. Ningun componente debe
// hardcodear URLs de la API. Sin slash final: todos los servicios
// concatenan `API_URL + "/ruta"`, y un slash doble rompe el ruteo
// (FastAPI no colapsa // intermedios -> 404).
export const API_URL = (
  import.meta.env.VITE_API_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export const api = axios.create({
  baseURL: API_URL,
  timeout: 90000,
});

// Adjunta el ID token de Firebase si hay sesion (persistente via
// browserLocalPersistence). Si no hay sesion, la peticion va sin header.
api.interceptors.request.use(async (config) => {
  try {
    const user = getAuth().currentUser;
    if (user) {
      const token = await user.getIdToken();
      config.headers = config.headers ?? {};
      (config.headers as Record<string, string>).Authorization =
        `Bearer ${token}`;
    }
  } catch {
    /* sin Firebase configurado: sigue sin auth */
  }
  return config;
});
