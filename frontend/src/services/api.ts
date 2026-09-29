import axios from "axios";

// La URL del backend SOLO vive aqui. Ningun componente debe
// hardcodear URLs de la API.
export const API_URL =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export const api = axios.create({
  baseURL: API_URL,
  timeout: 90000,
});
