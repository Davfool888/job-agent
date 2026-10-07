import { api } from "./api";

export interface AiKeyProvider {
  id: string;
  label: string;
  model: string;
  key_help: string;
}

export interface AiKeyStatus {
  id: string;
  label: string;
  model: string;
  key_help: string;
  configured: boolean;
  status: string;
  detail: string;
  updated_at: string | null;
}

export async function fetchAiProviders(): Promise<AiKeyProvider[]> {
  const { data } = await api.get<{ providers: AiKeyProvider[] }>(
    "/ai-keys/providers",
  );
  return data.providers;
}

export async function fetchAiStatus(): Promise<AiKeyStatus[]> {
  const { data } = await api.get<{ providers: Array<AiKeyStatus & { provider: string }> }>(
    "/ai-keys/status",
  );
  return data.providers.map((r) => ({
    id: r.provider,
    label: r.label,
    model: r.model,
    key_help: r.key_help,
    configured: r.configured,
    status: r.status,
    detail: r.detail,
    updated_at: r.updated_at,
  }));
}

export async function saveAiKey(
  provider: string,
  key: string,
): Promise<AiKeyStatus> {
  const { data } = await api.put<AiKeyStatus>(`/ai-keys/${provider}`, {
    key,
  });
  return data;
}

export async function deleteAiKey(provider: string): Promise<void> {
  await api.delete(`/ai-keys/${provider}`);
}

export function aiStatusLabel(status: string): string {
  switch (status) {
    case "disponible":
      return "disponible";
    case "cuota_agotada":
      return "cuota agotada";
    case "error":
      return "error";
    case "no_verificada":
      return "sin verificar";
    case "no_configurado":
      return "sin configurar";
    default:
      return status;
  }
}
