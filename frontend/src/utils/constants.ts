import type { JobStatus } from "../types/job";

export const STATUS_LABELS: Record<JobStatus, string> = {
  new: "Nueva",
  kept: "Conservada",
  discarded: "Descartada",
  opened: "Abierta",
  applied: "Postulada",
};

// Etiquetas legibles de cada fuente (clave = Job.source del backend).
export const SOURCE_LABELS: Record<string, string> = {
  computrabajo: "Computrabajo",
  magneto: "Magneto",
  elempleo: "ElEmpleo",
  indeed: "Indeed",
  linkedin: "LinkedIn",
};

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

export const DISCARD_REASONS = [
  "No coincide con mi perfil",
  "Requiere demasiada experiencia",
  "Salario",
  "Ubicación",
  "Modalidad",
  "Tecnologías que no manejo",
  "Tipo de cargo",
  "Empresa",
  "Otro",
] as const;

export const APPLICATION_STATUSES = [
  "pendiente",
  "iniciada",
  "aplicada",
  "entrevista",
  "rechazada",
  "proceso terminado",
] as const;
