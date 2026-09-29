import { api, API_URL } from "./api";

export interface CvGenerateResult {
  job_id: number;
  match_score: number | null;
  decision: "auto" | "forced" | "review_required" | "below_threshold";
  provider?: string | null;
  cv_generated: boolean;
  tex_path?: string | null;
  pdf_path?: string | null;
  pdf_ok?: boolean;
  download_tex?: string | null;
  download_pdf?: string | null;
  hint?: string;
}

export interface CvStatus {
  job_id: number;
  match_score: number | null;
  cv_generated: boolean;
  tex_path: string | null;
  pdf_path: string | null;
  download_tex: string | null;
  download_pdf: string | null;
}

export async function generateCv(
  jobId: number,
  force = false,
): Promise<CvGenerateResult> {
  const { data } = await api.post<CvGenerateResult>(`/jobs/${jobId}/cv`, {
    force,
  });
  return data;
}

export async function fetchCvStatus(jobId: number): Promise<CvStatus> {
  const { data } = await api.get<CvStatus>(`/jobs/${jobId}/cv`);
  return data;
}

export function cvDownloadUrl(
  jobId: number,
  format: "pdf" | "tex",
): string {
  return `${API_URL}/jobs/${jobId}/cv/download?format=${format}`;
}
