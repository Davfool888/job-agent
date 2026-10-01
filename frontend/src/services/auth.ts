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

export async function fetchAuthStatus(): Promise<{
  configured: boolean;
  provider: string;
  error?: string;
}> {
  const { data } = await api.get("/auth/status");
  return data;
}
