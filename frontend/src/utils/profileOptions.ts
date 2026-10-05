// Opciones y normalizacion para campos con vocabulario cerrado.
// La fuente primaria es GET /catalogs (backend); estos fallbacks locales
// solo se usan si el backend no responde, para no dejar selects vacios.

import { COLOMBIAN_CITIES } from "./cities";
import type { CatalogItem } from "../types/profile";

export const MODALITY_FALLBACK: CatalogItem[] = [
  { id: "ONSITE", label: "Presencial" },
  { id: "HYBRID", label: "Híbrido" },
  { id: "REMOTE", label: "Remoto" },
];

export const SENIORITY_FALLBACK: CatalogItem[] = [
  { id: "trainee", label: "Trainee / Practicante" },
  { id: "junior", label: "Junior" },
  { id: "mid", label: "Semi-senior" },
  { id: "senior", label: "Senior" },
  { id: "lead", label: "Lead / Líder técnico" },
  { id: "manager", label: "Manager / Gerente" },
];

export const SECTOR_FALLBACK: CatalogItem[] = [
  { id: "tecnologia", label: "Tecnología" },
  { id: "finanzas", label: "Servicios Financieros" },
  { id: "salud", label: "Salud" },
  { id: "educacion", label: "Educación" },
  { id: "comercio", label: "Comercio / Retail" },
  { id: "industria", label: "Industria / Manufactura" },
  { id: "servicios", label: "Servicios" },
  { id: "consultoria", label: "Consultoría" },
  { id: "gobierno", label: "Gobierno / Sector público" },
  { id: "telecom", label: "Telecomunicaciones" },
  { id: "logistica", label: "Logística / Transporte" },
  { id: "energia", label: "Energía" },
  { id: "construccion", label: "Construcción" },
  { id: "turismo", label: "Turismo / Hospitalidad" },
  { id: "medios", label: "Medios / Entretenimiento" },
  { id: "otro", label: "Otro" },
];

export const SALARY_CURRENCY_FALLBACK: CatalogItem[] = [
  { id: "COP", label: "COP ($)" },
  { id: "USD", label: "USD ($)" },
  { id: "MXN", label: "MXN ($)" },
  { id: "EUR", label: "EUR (€)" },
  { id: "CLP", label: "CLP ($)" },
  { id: "PEN", label: "PEN (S/)" },
  { id: "ARS", label: "ARS ($)" },
];

export const SALARY_PERIOD_FALLBACK: CatalogItem[] = [
  { id: "mensual", label: "Mensual" },
  { id: "anual", label: "Anual" },
  { id: "hora", label: "Por hora" },
  { id: "proyecto", label: "Por proyecto" },
];

export const ENTRY_STATUS_FALLBACK: CatalogItem[] = [
  { id: "finished", label: "Finalizado" },
  { id: "in_progress", label: "En curso" },
  { id: "abandoned", label: "Abandonado" },
];

export const SOFT_SKILLS_FALLBACK: string[] = [
  "Comunicación",
  "Comunicación asertiva",
  "Trabajo en equipo",
  "Liderazgo",
  "Pensamiento analítico",
  "Pensamiento crítico",
  "Resolución de problemas",
  "Toma de decisiones",
  "Adaptabilidad",
  "Gestión del tiempo",
  "Atención al detalle",
  "Orientación a resultados",
  "Proactividad",
  "Creatividad",
  "Negociación",
  "Inteligencia emocional",
  "Empatía",
  "Ética profesional",
];

// Categorias de rol que el motor de matching ya detecta
// (backend/app/analysis/domains.py): usarlas como texto canonico en
// perspectivas evita variantes que no puntuan.
export const TITLE_CATEGORY_SUGGESTIONS: string[] = [
  "DATA_ANALYST",
  "BI_ANALYST",
  "DATA_ENGINEER",
  "DATA_SCIENTIST",
  "BACKEND_DEVELOPER",
  "FRONTEND_DEVELOPER",
  "FULLSTACK_DEVELOPER",
  "SOFTWARE_DEVELOPER",
  "DEVOPS_ENGINEER",
  "QA_ENGINEER",
  "DATABASE_ADMIN",
  "ML_ENGINEER",
  "BUSINESS_ANALYST",
  "PROJECT_MANAGER",
  "PRODUCT_MANAGER",
];

export const DOMAIN_SUGGESTIONS: string[] = [
  "Retail",
  "Servicios Financieros",
  "Salud",
  "Educación",
  "Tecnología",
  "Industria",
  "Logística",
  "Energía",
  "Construcción",
  "Turismo",
  "Gobierno",
  "Telecomunicaciones",
  "Consultoría",
  "Comercio",
  "Medios",
];

/** Minusculas sin tildes para comparar variantes ("Bogotá" = "bogota"). */
export function normText(value: string | null | undefined): string {
  return (value ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ");
}

/**
 * Nombre completo -> [nombres, apellidos], convencion hispana.
 * Los dos primeros tokens son nombres ("David Santiago Herrera
 * Reales" -> ["David Santiago", "Herrera Reales"]). Misma regla que
 * el backend (catalogs.split_spanish_name).
 */
export function splitSpanishName(full: string | null | undefined): [string, string] {
  const parts = (full ?? "").split(/\s+/).filter(Boolean);
  if (parts.length <= 2) return [parts[0] ?? "", parts.slice(1).join(" ")];
  return [parts.slice(0, 2).join(" "), parts.slice(2).join(" ")];
}

/**
 * Resuelve un valor guardado (id o label, con o sin tildes) al id
 * canonico del catalogo. Devuelve null si no coincide (variante libre).
 */
export function resolveOptionId(
  value: string | null | undefined,
  options: CatalogItem[],
): string | null {
  if (!value || !value.trim()) return null;
  const raw = value.trim();
  if (options.some((o) => o.id === raw)) return raw;
  const wanted = normText(raw);
  // "Bogotá, Colombia" / "Bogotá D.C." -> "bogota"
  const first = wanted
    .split(",")[0]
    .trim()
    .replace(/\s+d\.?\s*c\.?$/, "")
    .replace(/\s+dc$/, "")
    .trim();
  for (const o of options) {
    if (normText(o.label) === wanted || normText(o.label) === first) {
      return o.id;
    }
    if (o.id.replace(/_/g, " ") === wanted) return o.id;
  }
  return null;
}

/** Etiqueta para mostrar un valor guardado (id o label). */
export function optionLabel(
  value: string | null | undefined,
  options: CatalogItem[],
): string {
  const id = resolveOptionId(value, options);
  if (id) return options.find((o) => o.id === id)?.label ?? value ?? "";
  return value ?? "";
}

/** Etiqueta canonica de una ciudad o el texto original si no coincide. */
export function canonicalLocation(
  value: string | null | undefined,
  cities: string[] = COLOMBIAN_CITIES,
): string {
  const text = (value ?? "").trim();
  if (!text) return "";
  const items: CatalogItem[] = cities.map((c) => ({ id: c, label: c }));
  const id = resolveOptionId(text, items);
  return id ?? text;
}

/** Des-duplica variantes del scraper ("Bogotá, D.C." + "Bogotá" -> "Bogotá"). */
export function uniqueCanonicalLocations(
  values: Array<string | null>,
  cities: string[] = COLOMBIAN_CITIES,
): string[] {
  const seen = new Map<string, string>();
  for (const v of values) {
    const text = (v ?? "").trim();
    if (!text) continue;
    const canonical = canonicalLocation(text, cities);
    const key = normText(canonical);
    if (!seen.has(key)) seen.set(key, canonical);
  }
  return [...seen.values()].sort((a, b) => a.localeCompare(b));
}

/** Extrae {amount, currency, period} del string guardado de salario. */
export function parseSalaryString(value: string): {
  amount: string;
  currency: string;
  period: string;
} {
  const out = { amount: "", currency: "", period: "" };
  const text = (value ?? "").trim();
  if (!text) return out;
  const m = text.match(/^([\d][\d.,]*)\s*([A-Za-z]{3})?\s*(.*)$/);
  if (!m) return out;
  out.amount = m[1].replace(/[.,]/g, "");
  if (m[2]) {
    const cur = m[2].toUpperCase();
    if (SALARY_CURRENCY_FALLBACK.some((c) => c.id === cur)) {
      out.currency = cur;
    }
  }
  if (m[3] && m[3].trim()) {
    const periodId = resolveOptionId(m[3].trim(), SALARY_PERIOD_FALLBACK);
    out.period = periodId ?? "";
  }
  return out;
}
