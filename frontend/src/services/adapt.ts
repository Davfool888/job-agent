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
  const { data } = await api.post<AdaptCvResult>(`/jobs/${jobId}/adapt-cv`);
  if (!data.success) {
    throw new Error(data.error?.message ?? "No fue posible generar el CV.");
  }
  return data;
}

export function adaptDownloadUrl(
  jobId: number | string,
  format: "pdf" | "html" = "pdf",
): string {
  return `${API_URL}/jobs/${jobId}/adapt-cv/download?format=${format}`;
}
