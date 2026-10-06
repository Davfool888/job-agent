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

export type ProfileIncompleteError = Error & {
  code: "PROFILE_INCOMPLETE";
};

export const ADAPT_STAGES = [
  "Analizando oferta…",
  "Personalizando perfil…",
  "Generando curriculum…",
] as const;

// --- Flujo asincrono (POST rapido + polling, evita el timeout de 90s) ---

export interface AdaptStartAccepted {
  accepted: boolean;
  job_id: string;
  status: "processing" | "done";
}

export type AdaptJobStatus =
  | { status: "idle"; job_id: string }
  | { status: "processing"; job_id: string; started_at?: string }
  | { status: "done"; job_id: string; result: AdaptCvResult }
  | {
      status: "error";
      job_id: string;
      error: { code: string; message: string };
    };

export type AdaptErrorCode =
  | "PROFILE_INCOMPLETE"
  | "NO_RESPONSE"
  | "POLL_TIMEOUT"
  | string;

export type AdaptAsyncError = Error & { code: AdaptErrorCode };

// Mensaje por codigo de error del backend (app/adapt/*). Cada fallo
// explica su causa en vez del generico "no respondio a tiempo".
export function adaptErrorMessage(code: string, fallback?: string): string {
  switch (code) {
    case "PROFILE_INCOMPLETE":
      return (
        "Tu perfil está incompleto. Ve a la sección de Perfil y completa " +
        "nombre, email, teléfono y al menos una experiencia o estudio."
      );
    case "JOB_NOT_FOUND":
      return "La oferta ya no existe en la base de datos.";
    case "JOB_INCOMPLETE":
      return "La oferta no tiene datos suficientes (sin título ni descripción) para adaptar el CV.";
    case "BROWSER_MISSING":
      return (
        "El motor PDF se está instalando en el servidor. Espera 2 minutos " +
        "y pulsa «Adaptar perfil» de nuevo."
      );
    case "PDF_BUSY":
      return (
        "El servidor está generando otro PDF. Tu tarea sigue en cola: " +
        "espera 1 minuto (el polling reintenta solo)."
      );
    case "PDF_TIMEOUT":
      return (
        "Generar el PDF excedió el tiempo límite (servidor saturado). " +
        "Reintenta en 1 minuto."
      );
    case "PDF_EMPTY_HTML":
    case "PDF_EMPTY_FILE":
    case "PDF_INVALID_FILE":
    case "PDF_GENERATION_FAILED":
    case "HTML_FAILED":
      return `No fue posible generar el PDF (${code}). Reintenta; si persiste, revisa tu perfil.`;
    case "STALE_JOB":
      return (
        "El proceso se interrumpió (servidor reiniciado). " +
        "Pulsa «Adaptar perfil» de nuevo."
      );
    case "NO_RESPONSE":
      return (
        "No se pudo iniciar la adaptación (instancia gratuita dormida o " +
        "sin red). Espera 1 minuto y reintenta."
      );
    case "POLL_TIMEOUT":
      return (
        "Sigue procesando en el servidor (cola de PDFs o instancia lenta). " +
        "Vuelve en 1 minuto y pulsa «Adaptar perfil» de nuevo: retoma donde quedó."
      );
    default:
      return fallback || `Falló la adaptación (${code}). Reintenta en 1 minuto.`;
  }
}

function toAsyncError(code: string, message: string): AdaptAsyncError {
  const error = new Error(message) as AdaptAsyncError;
  error.code = code;
  return error;
}

function isNoResponse(e: unknown): boolean {
  return (
    typeof e === "object" &&
    e !== null &&
    "request" in e &&
    !("response" in e && (e as { response?: unknown }).response)
  );
}

function backendErrorOf(e: unknown): { code: string; message: string } | null {
  // El backend async devuelve {success:false, error:{code,message}} con
  // status != 2xx; axios lo entrega en e.response.data.
  if (typeof e === "object" && e !== null && "response" in e) {
    const data = (e as { response?: { data?: unknown } }).response?.data as
      | { error?: { code?: unknown; message?: unknown }; success?: unknown }
      | undefined;
    if (data && typeof data === "object" && "error" in data) {
      const err = (data as { error?: { code?: unknown; message?: unknown } }).error;
      if (err && typeof err.code === "string") {
        return {
          code: err.code,
          message:
            typeof err.message === "string" && err.message
              ? err.message
              : adaptErrorMessage(err.code),
        };
      }
    }
  }
  return null;
}

// POST rapido: solo valida (job + perfil) y encola el worker. Responde 202
// en ms, asi que un timeout corto basta; si el 202 llega, el PDF se genera
// en fondo aunque el cliente siga en polling.
export async function startAdaptCv(
  jobId: number | string,
): Promise<AdaptStartAccepted> {
  try {
    const { data } = await api.post<AdaptStartAccepted>(
      `/jobs/${jobId}/adapt-cv/start`,
      null,
      { timeout: 30000 },
    );
    return data;
  } catch (e) {
    const backend = backendErrorOf(e);
    if (backend) throw toAsyncError(backend.code, backend.message);
    if (isNoResponse(e)) {
      throw toAsyncError("NO_RESPONSE", adaptErrorMessage("NO_RESPONSE"));
    }
    throw e;
  }
}

export async function getAdaptStatus(
  jobId: number | string,
): Promise<AdaptJobStatus> {
  const { data } = await api.get<AdaptJobStatus>(
    `/jobs/${jobId}/adapt-cv/status`,
  );
  return data;
}

export interface PollAdaptOptions {
  intervalMs?: number;
  timeoutMs?: number;
  onPoll?: (attempt: number, status: AdaptJobStatus) => void;
}

// Espera hasta done/error. Resuelve con el AdaptCvResult del servidor;
// rechaza con AdaptAsyncError con code especifico (ver adaptErrorMessage).
export async function pollAdaptCv(
  jobId: number | string,
  options: PollAdaptOptions = {},
): Promise<AdaptCvResult> {
  const intervalMs = options.intervalMs ?? 3000;
  const timeoutMs = options.timeoutMs ?? 6 * 60 * 1000;
  const started = Date.now();
  let attempt = 0;
  for (;;) {
    let status: AdaptJobStatus;
    try {
      status = await getAdaptStatus(jobId);
    } catch (e) {
      if (isNoResponse(e)) {
        // Corte durante el polling: el worker sigue en el servidor.
        // Se sigue intentando hasta el timeout global en vez de fallar ya.
        if (Date.now() - started > timeoutMs) {
          throw toAsyncError("POLL_TIMEOUT", adaptErrorMessage("POLL_TIMEOUT"));
        }
        await new Promise((r) => setTimeout(r, intervalMs));
        continue;
      }
      throw e;
    }
    options.onPoll?.(attempt++, status);
    if (status.status === "done") return status.result;
    if (status.status === "error") {
      const code = status.error.code || "UNKNOWN_ERROR";
      throw toAsyncError(code, status.error.message || adaptErrorMessage(code));
    }
    if (Date.now() - started > timeoutMs) {
      throw toAsyncError("POLL_TIMEOUT", adaptErrorMessage("POLL_TIMEOUT"));
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

// Flujo completo asincrono: start + poll. Mantiene la misma firma de
// resultado que el sync para no tocar el resto de la UI.
export async function adaptCvAsync(
  jobId: number | string,
  options: PollAdaptOptions = {},
): Promise<AdaptCvResult> {
  await startAdaptCv(jobId);
  return pollAdaptCv(jobId, options);
}

export async function adaptCv(
  jobId: number | string,
): Promise<AdaptCvResult> {
  try {
    const { data } = await api.post<AdaptCvResult>(`/jobs/${jobId}/adapt-cv`);
    if (!data.success) {
      // Extraer el código de error si existe
      const error = new Error(data.error?.message ?? "No fue posible generar el CV.") as ProfileIncompleteError;
      error.code = (data.error?.code === "PROFILE_INCOMPLETE" ? "PROFILE_INCOMPLETE" : "UNKNOWN_ERROR") as "PROFILE_INCOMPLETE";
      throw error;
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
  idToken?: string | null,
): string {
  const base = `${API_URL}/jobs/${jobId}/adapt-cv/download?format=${format}`;
  // El iframe/<a> no envia Authorization: el token viaja como ?token=
  // (mismo patron que el stream de busqueda). Sin token el backend
  // resuelve como invitado y jamas debe mostrarse archivo ajeno.
  return idToken ? `${base}&token=${encodeURIComponent(idToken)}` : base;
}
