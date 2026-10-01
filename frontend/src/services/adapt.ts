import { api, API_URL } from "./api";

export interface AdaptCvResult {
  success: boolean;
  job: { id: string; title: string; company: string };
  matching: {
    percentage: number;
    matched_skills: string[];
    missing_skills: string[];
  };
  cv: {
    id: string;
    summary_provider: string;
    experiences: Array<{ title: string; company: string }>;
    projects: string[];
    download_url: string;
    preview_url: string;
  };
  error?: { code: string; message: string };
}

export const ADAPT_STAGES = [
  "Analizando oferta…",
  "Personalizando perfil…",
  "Generando curriculum…",
] as const;

export async function adaptCv(
  jobId: number | string,
): Promise<AdaptCvResult> {
  try {
    const { data } = await api.post<AdaptCvResult>(`/jobs/${jobId}/adapt-cv`);
    if (!data.success) {
      throw new Error(data.error?.message ?? "No fue posible generar el CV.");
    }
    return data;
  } catch (e) {
    // Sin respuesta del servidor (timeout, instancia dormida o caida):
    // el navegador lo muestra como fallo de red/CORS.
    if (
      typeof e === "object" &&
      e !== null &&
      "request" in e &&
      !("response" in e && (e as { response?: unknown }).response)
    ) {
      throw new Error(
        "El servidor no respondió a tiempo (instancia gratuita dormida o " +
          "saturada generando el PDF). Espera 1 minuto y reintenta.",
      );
    }
    throw e;
  }
}

export function adaptDownloadUrl(
  jobId: number | string,
  format: "pdf" | "html" = "pdf",
): string {
  return `${API_URL}/jobs/${jobId}/adapt-cv/download?format=${format}`;
}
