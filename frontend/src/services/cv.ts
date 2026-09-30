import { api, API_URL } from "./api";

export interface CvGenerateResult {
  job_id: number | string;
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
  job_id: number | string;
  match_score: number | null;
  cv_generated: boolean;
  tex_path: string | null;
  pdf_path: string | null;
  download_tex: string | null;
  download_pdf: string | null;
}

export async function generateCv(
  jobId: number | string,
  force = false,
): Promise<CvGenerateResult> {
  const { data } = await api.post<CvGenerateResult>(`/jobs/${jobId}/cv`, {
    force,
  });
  return data;
}

export async function fetchCvStatus(jobId: number | string): Promise<CvStatus> {
  const { data } = await api.get<CvStatus>(`/jobs/${jobId}/cv`);
  return data;
}

export type CustomizedCvState = "NOT_GENERATED" | "READY" | "ERROR";

export interface CustomizedCv {
  state: CustomizedCvState;
  job_id: number | string;
  version?: number;
  analysis?: Record<string, unknown> | null;
  selected_experience?: Array<Record<string, unknown>>;
  selected_skills?: string[];
  generated_content?: Record<string, unknown> | null;
  latex_available?: boolean;
  pdf_available?: boolean;
  created_at?: string | null;
  download_tex?: string | null;
  download_pdf?: string | null;
  error?: string;
  hint?: string;
}

export async function fetchCustomizedCv(
  jobId: number | string,
): Promise<CustomizedCv> {
  const { data } = await api.get<CustomizedCv>(
    `/jobs/${jobId}/customized-cv`,
  );
  return data;
}

export function cvDownloadUrl(
  jobId: number | string,
  format: "pdf" | "tex",
): string {
  return `${API_URL}/jobs/${jobId}/cv/download?format=${format}`;
}
