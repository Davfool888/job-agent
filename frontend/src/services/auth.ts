import { api } from "./api";

export interface BackendUser {
  uid: string;
  email: string;
  nombre: string;
  telefono: string;
  created_at?: string | null;
  updated_at?: string | null;
  is_new?: boolean;
  is_profile_complete?: boolean;
}

export async function fetchMe(idToken: string): Promise<BackendUser> {
  const { data } = await api.get<BackendUser>("/auth/me", {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  return data;
}

export async function updateMe(
  idToken: string,
  payload: { nombre?: string; telefono?: string },
): Promise<BackendUser> {
  const { data } = await api.put<BackendUser>("/auth/me", payload, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  return data;
}

export type AuthApiError = Error & { code?: string; status?: number };

function throwApiError(e: unknown, fallback: string): never {
  const resp = (e as { response?: { status?: number; data?: unknown } })
    ?.response;
  const data = resp?.data as
    | { code?: unknown; message?: unknown; detail?: unknown }
    | undefined;
  const message =
    (typeof data?.message === "string" && data.message) ||
    (typeof data?.detail === "string" && data.detail) ||
    fallback;
  const err = new Error(message) as AuthApiError;
  err.status = resp?.status;
  err.code = typeof data?.code === "string" ? data.code : undefined;
  throw err;
}

// Registro estricto: 201 crea, 409 si ya existe (no pisa).
export async function registerAccount(
  idToken: string,
  payload: { nombre: string; telefono: string },
): Promise<BackendUser> {
  try {
    const { data } = await api.post<BackendUser>("/auth/register", payload, {
      headers: { Authorization: `Bearer ${idToken}` },
    });
    return data;
  } catch (e) {
    throwApiError(e, "No se pudo registrar.");
  }
}

// Entrada estricta: 200 si hay registro, 404 si no.
export async function loginAccount(idToken: string): Promise<BackendUser> {
  try {
    const { data } = await api.post<BackendUser>("/auth/login", null, {
      headers: { Authorization: `Bearer ${idToken}` },
    });
    return data;
  } catch (e) {
    throwApiError(e, "No se pudo entrar.");
  }
}

export async function fetchAuthStatus(): Promise<{
  configured: boolean;
  provider: string;
  error?: string;
}> {
  const { data } = await api.get("/auth/status");
  return data;
}
