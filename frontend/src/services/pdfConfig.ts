import { api } from "./api";

export interface PDFConfig {
  font_family: string;
  font_size_pt: number;
  section_order: string[];
  date_format: string;
  show_skill_chips: boolean;
  compact_mode: boolean;
  header_style: string;
  section_divider: string;
  margin_top_mm: number;
  margin_bottom_mm: number;
  margin_left_mm: number;
  margin_right_mm: number;
  section_spacing_pt: number;
  accent_color: string;
  max_projects: number;
  max_experiences: number;
  max_bullets: number;
  profile_length: string;
  show_soft_skills: boolean;
  show_courses: boolean;
  show_languages: boolean;
  show_links: boolean;
  max_pages: number;
}

export interface PDFConfigUpdate {
  font_family?: string;
  font_size_pt?: number;
  section_order?: string[];
  date_format?: string;
  show_skill_chips?: boolean;
  compact_mode?: boolean;
  header_style?: string;
  section_divider?: string;
  margin_top_mm?: number;
  margin_bottom_mm?: number;
  margin_left_mm?: number;
  margin_right_mm?: number;
  section_spacing_pt?: number;
  accent_color?: string;
  max_projects?: number;
  max_experiences?: number;
  max_bullets?: number;
  profile_length?: string;
  show_soft_skills?: boolean;
  show_courses?: boolean;
  show_languages?: boolean;
  show_links?: boolean;
  max_pages?: number;
}

export async function fetchPDFConfig(): Promise<PDFConfig> {
  const { data } = await api.get<PDFConfig>("/pdf-config");
  return data;
}

export async function updatePDFConfig(payload: PDFConfigUpdate): Promise<PDFConfig> {
  const { data } = await api.put<PDFConfig>("/pdf-config", payload);
  return data;
}

export async function resetPDFConfig(): Promise<PDFConfig> {
  const { data } = await api.post<PDFConfig>("/pdf-config/reset");
  return data;
}