import { useEffect, useState } from "react";
import { Header } from "../components/layout/Header";
import { API_URL } from "../services/api";
import { checkHealth } from "../services/jobs";
import { useTheme, type Theme } from "../hooks/useTheme";
import { fetchPDFConfig, updatePDFConfig, resetPDFConfig, type PDFConfig, type PDFConfigUpdate } from "../services/pdfConfig";
import { fetchSearchConfig, fetchSearchOptions, updateSearchConfig, type FitConfig, type FitOptions } from "../services/searchConfig";
import { FitFields } from "../components/search/FitFields";

const FONT_FAMILIES = [
  { value: "georgia", label: "Georgia (clásica, serif)" },
  { value: "times", label: "Times New Roman (formal, serif)" },
  { value: "arial", label: "Arial (moderna, sans-serif)" },
] as const;

const DATE_FORMATS = [
  { value: "MM/YYYY", label: "MM/YYYY (ej: 03/2026)" },
  { value: "MM/YY", label: "MM/YY (ej: 03/26)" },
  { value: "MMMM YYYY", label: "MMMM YYYY (ej: Marzo 2026)" },
  { value: "YYYY-MM", label: "YYYY-MM (ej: 2026-03)" },
] as const;

const HEADER_STYLES = [
  { value: "classic", label: "Clásica (línea inferior + nombre grande)" },
  { value: "modern", label: "Moderna (centrado, sin línea)" },
  { value: "minimal", label: "Minimalista (solo nombre y contacto)" },
] as const;

const SECTION_DIVIDERS = [
  { value: "line", label: "Línea simple" },
  { value: "double", label: "Doble línea" },
  { value: "dots", label: "Puntos" },
  { value: "none", label: "Sin divisor" },
] as const;

const FONT_SIZES = [10, 11, 12, 14, 16] as const;

const AVAILABLE_SECTIONS = [
  { slug: "summary", label: "Perfil Profesional" },
  { slug: "experience", label: "Experiencia Profesional" },
  { slug: "education", label: "Educación" },
  { slug: "projects", label: "Proyectos Destacados" },
  { slug: "skills", label: "Competencias Técnicas" },
  { slug: "soft_skills", label: "Habilidades Blandas" },
  { slug: "languages", label: "Idiomas" },
  { slug: "other_studies", label: "Otros Estudios" },
  { slug: "other_knowledge", label: "Otros Conocimientos" },
  { slug: "certifications", label: "Certificaciones" },
] as const;

function SectionOrderEditor({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const available = AVAILABLE_SECTIONS.filter(s => !value.includes(s.slug));

  const move = (from: number, to: number) => {
    if (from === to) return;
    const next = [...value];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    onChange(next);
  };

  return (
    <div className="field">
      <label>Orden de secciones</label>
      <p className="card-sub" style={{ marginBottom: 8 }}>
        Arrastra para reordenar (o usa las flechas). Secciones disponibles:
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {value.map((slug, idx) => {
          const section = AVAILABLE_SECTIONS.find(s => s.slug === slug);
          if (!section) return null;
          const dragging = dragIdx === idx;
          return (
            <div
              key={slug}
              className="card"
              draggable
              onDragStart={e => {
                setDragIdx(idx);
                e.dataTransfer.effectAllowed = "move";
              }}
              onDragOver={e => e.preventDefault()}
              onDrop={e => {
                e.preventDefault();
                if (dragIdx !== null) move(dragIdx, idx);
                setDragIdx(null);
              }}
              onDragEnd={() => setDragIdx(null)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: 8,
                opacity: dragging ? 0.5 : 1,
                cursor: "grab",
              }}
            >
              <span style={{ cursor: "grab", fontSize: 18 }} title="Arrastra para mover">⋮⋮</span>
              <span style={{ flex: 1 }}>{section.label}</span>
              <button
                className="btn btn-ghost btn-sm"
                disabled={idx === 0}
                onClick={() => move(idx, idx - 1)}
                title="Subir"
              >
                ↑
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={idx === value.length - 1}
                onClick={() => move(idx, idx + 1)}
                title="Bajar"
              >
                ↓
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  const next = [...value];
                  next.splice(idx, 1);
                  onChange(next);
                }}
                title="Eliminar"
              >
                ✕
              </button>
            </div>
          );
        })}
        {available.length > 0 && (
          <div className="card" style={{ padding: 8 }}>
            <span className="card-sub">Disponibles: </span>
            {available.map(s => (
              <button
                key={s.slug}
                className="btn btn-ghost btn-xs"
                style={{ margin: 2 }}
                onClick={() => onChange([...value, s.slug])}
              >
                + {s.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function NumberInput({ label, value, onChange, min, max, step = 1, suffix }: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
}) {
  return (
    <div className="field" style={{ maxWidth: 160 }}>
      <label>{label}</label>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <input
          type="number"
          className="select"
          value={value}
          onChange={e => onChange(Math.max(min ?? -Infinity, Math.min(max ?? Infinity, parseInt(e.target.value) || 0)))}
          min={min}
          max={max}
          step={step}
          style={{ width: 80 }}
        />
        {suffix && <span style={{ color: "var(--text-muted)", fontSize: 13 }}>{suffix}</span>}
      </div>
    </div>
  );
}

export function Settings() {
  const { theme, setTheme } = useTheme();
  const [health, setHealth] = useState<string>("Sin comprobar");
  const [checking, setChecking] = useState(false);
  const [pdfConfig, setPdfConfig] = useState<PDFConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [fitConfig, setFitConfig] = useState<FitConfig | null>(null);
  const [fitOptions, setFitOptions] = useState<FitOptions | null>(null);
  const [fitSaving, setFitSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const ping = async () => {
    setChecking(true);
    const ok = await checkHealth();
    setHealth(ok ? "Backend responde OK" : "Backend no responde");
    setChecking(false);
  };

  const loadConfig = async () => {
    try {
      const config = await fetchPDFConfig();
      setPdfConfig(config);
    } catch (e) {
      console.error("Error cargando config PDF:", e);
    } finally {
      setLoading(false);
    }
    try {
      const [fit, options] = await Promise.all([
        fetchSearchConfig().catch(() => null),
        fetchSearchOptions().catch(() => null),
      ]);
      if (fit) setFitConfig(fit);
      if (options) setFitOptions(options);
    } catch (e) {
      console.error("Error cargando config de búsqueda:", e);
    }
  };

  const handleFitUpdate = async (patch: Partial<FitConfig>) => {
    setFitSaving(true);
    setMessage(null);
    try {
      const updated = await updateSearchConfig(patch);
      setFitConfig(updated);
      setMessage({ type: "success", text: "Búsqueda configurada correctamente" });
    } catch (e: any) {
      console.error(e);
      setMessage({ type: "error", text: e.response?.data?.detail || "Error al guardar" });
    } finally {
      setFitSaving(false);
    }
  };

  const handleUpdate = async (updates: PDFConfigUpdate) => {
    if (!pdfConfig) return;
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updatePDFConfig(updates);
      setPdfConfig(updated);
      setMessage({ type: "success", text: "Configuración guardada correctamente" });
    } catch (e: any) {
      console.error(e);
      setMessage({ type: "error", text: e.response?.data?.detail || "Error al guardar" });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm("¿Seguro que quieres restablecer la configuración por defecto?")) return;
    setSaving(true);
    setMessage(null);
    try {
      const reset = await resetPDFConfig();
      setPdfConfig(reset);
      setMessage({ type: "success", text: "Configuración restablecida por defecto" });
    } catch (e: any) {
      console.error(e);
      setMessage({ type: "error", text: e.response?.data?.detail || "Error al restablecer" });
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  if (!pdfConfig && loading) {
    return (
      <>
        <Header title="Configuración" subtitle="Preferencias de generación de PDF" />
        <div className="content">Cargando configuración…</div>
      </>
    );
  }

  return (
    <>
      <Header title="Configuración" subtitle="Conexión, apariencia y generación de PDF" />
      <div className="content">
        {message && (
          <div className={`card`} style={{ marginBottom: 16, background: message.type === "success" ? "var(--success-bg)" : "var(--danger-bg)", color: message.type === "success" ? "var(--success)" : "var(--danger)" }}>
            {message.text}
          </div>
        )}

        <div className="card" style={{ marginBottom: 16 }}>
          <h3 className="card-title">Backend</h3>
          <p className="card-sub">
            La URL vive en <code>frontend/.env</code> como{" "}
            <code>VITE_API_URL</code> (actual: {API_URL}).
          </p>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <button className="btn btn-ghost btn-sm" onClick={ping} disabled={checking}>
              {checking ? "Comprobando…" : "Probar conexión"}
            </button>
            <span style={{ fontSize: 13 }}>{health}</span>
          </div>
        </div>

        <div className="card" style={{ marginBottom: 16 }}>
          <h3 className="card-title">Apariencia</h3>
          <p className="card-sub">
            Solo preferencia visual guardada en este navegador.
          </p>
          <div className="field" style={{ maxWidth: 260 }}>
            <label>Tema</label>
            <select
              className="select"
              value={theme}
              onChange={(e) => setTheme(e.target.value as Theme)}
            >
              <option value="oscuro">Oscuro</option>
              <option value="claro">Claro</option>
              <option value="sistema">Seguir al sistema</option>
            </select>
          </div>
        </div>

        {fitConfig && (
          <div className="card" style={{ marginBottom: 16 }}>
            <h3 className="card-title">Configuración de búsqueda</h3>
            <p className="card-sub">
              Vale para el <strong>Dashboard</strong> y como base de las{" "}
              <strong>búsquedas automáticas</strong>. Cada perfil puede
              sobreescribirla (vacío = usa esta). Solo se descartan ofertas
              que <strong>contradigan</strong> el rango en título o
              descripción; sin dato, la oferta pasa.
            </p>
            <FitFields
              value={fitConfig}
              options={fitOptions}
              disabled={fitSaving}
              onChange={(patch) => void handleFitUpdate(patch)}
            />
          </div>
        )}

        {pdfConfig && (
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 className="card-title">Configuración de PDF</h3>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={handleReset}
                  disabled={saving}
                >
                  Restablecer por defecto
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => handleUpdate({})}
                  disabled={saving}
                >
                  {saving ? "Guardando…" : "Guardar cambios"}
                </button>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
              {/* Fuente y tamaño */}
              <div className="field">
                <label>Fuente</label>
                <select
                  className="select"
                  value={pdfConfig.font_family}
                  onChange={e => handleUpdate({ font_family: e.target.value })}
                >
                  {FONT_FAMILIES.map(f => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </select>
              </div>

              <div className="field">
                <label>Tamaño de fuente</label>
                <select
                  className="select"
                  value={String(pdfConfig.font_size_pt)}
                  onChange={e => handleUpdate({ font_size_pt: Number(e.target.value) })}
                >
                  {FONT_SIZES.map(size => (
                    <option key={size} value={size}>{size} pt</option>
                  ))}
                </select>
              </div>

              {/* Formato de fecha */}
              <div className="field">
                <label>Formato de fecha</label>
                <select
                  className="select"
                  value={pdfConfig.date_format}
                  onChange={e => handleUpdate({ date_format: e.target.value })}
                >
                  {DATE_FORMATS.map(f => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </select>
              </div>

              {/* Estilo de cabecera */}
              <div className="field">
                <label>Estilo de cabecera</label>
                <select
                  className="select"
                  value={pdfConfig.header_style}
                  onChange={e => handleUpdate({ header_style: e.target.value })}
                >
                  {HEADER_STYLES.map(h => (
                    <option key={h.value} value={h.value}>{h.label}</option>
                  ))}
                </select>
              </div>

              {/* Divisor de secciones */}
              <div className="field">
                <label>Divisor de secciones</label>
                <select
                  className="select"
                  value={pdfConfig.section_divider}
                  onChange={e => handleUpdate({ section_divider: e.target.value })}
                >
                  {SECTION_DIVIDERS.map(d => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </select>
              </div>

              {/* Modo compacto */}
              <div className="field" style={{ display: "flex", alignItems: "flex-end" }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <input
                    type="checkbox"
                    checked={pdfConfig.compact_mode}
                    onChange={e => handleUpdate({ compact_mode: e.target.checked })}
                  />
                  <span className="card-sub">Modo compacto (menos espaciado)</span>
                </label>
              </div>

              {/* Mostrar chips de skills */}
              <div className="field" style={{ display: "flex", alignItems: "flex-end" }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <input
                    type="checkbox"
                    checked={pdfConfig.show_skill_chips}
                    onChange={e => handleUpdate({ show_skill_chips: e.target.checked })}
                  />
                  <span className="card-sub">Mostrar chips de skills</span>
                </label>
              </div>

              {/* Color: siempre negro (sin selector) */}

              {/* Márgenes fijas norma APA (25 mm en los 4 lados) */}
              <div className="field">
                <label>Márgenes</label>
                <p className="card-sub" style={{ margin: 0 }}>
                  Fijas norma APA: 25 mm en los 4 lados.
                </p>
              </div>

              {/* Espaciado entre secciones */}
              <NumberInput
                label="Espaciado entre secciones (pt)"
                value={pdfConfig.section_spacing_pt}
                onChange={v => handleUpdate({ section_spacing_pt: v })}
                min={4}
                max={30}
                step={1}
                suffix="pt"
              />

              {/* Orden de secciones */}
              <SectionOrderEditor
                value={pdfConfig.section_order}
                onChange={v => handleUpdate({ section_order: v })}
              />

              {/* Contenido del CV adaptado (manda sobre la relevancia) */}
              <div className="field">
                <label>Máx. experiencias</label>
                <select
                  className="select"
                  value={String(pdfConfig.max_experiences ?? 3)}
                  onChange={e => handleUpdate({ max_experiences: Number(e.target.value) })}
                  title="Aunque haya más relevantes, salen estas"
                >
                  {[1, 2, 3, 4, 5].map(n => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </div>

              <div className="field">
                <label>Máx. proyectos</label>
                <select
                  className="select"
                  value={String(pdfConfig.max_projects ?? 3)}
                  onChange={e => handleUpdate({ max_projects: Number(e.target.value) })}
                >
                  {[1, 2, 3, 4, 5].map(n => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </div>

              <div className="field">
                <label>Bullets por experiencia (0 = sin límite)</label>
                <select
                  className="select"
                  value={String(pdfConfig.max_bullets ?? 0)}
                  onChange={e => handleUpdate({ max_bullets: Number(e.target.value) })}
                >
                  {[0, 2, 3, 4, 5, 6].map(n => (
                    <option key={n} value={n}>{n === 0 ? "Sin límite" : n}</option>
                  ))}
                </select>
              </div>

              <div className="field">
                <label>Longitud del perfil</label>
                <select
                  className="select"
                  value={pdfConfig.profile_length ?? "full"}
                  onChange={e => handleUpdate({ profile_length: e.target.value })}
                  title="Corto/medio recortan por oraciones, sin reescribir"
                >
                  <option value="short">Corto (~450 caracteres)</option>
                  <option value="medium">Medio (~900 caracteres)</option>
                  <option value="full">Completo</option>
                </select>
              </div>

              <div className="field">
                <label>Máx. páginas (0 = sin límite)</label>
                <select
                  className="select"
                  value={String(pdfConfig.max_pages ?? 0)}
                  onChange={e => handleUpdate({ max_pages: Number(e.target.value) })}
                  title="Si se excede, se regenera compacto una vez"
                >
                  {[0, 1, 2, 3].map(n => (
                    <option key={n} value={n}>{n === 0 ? "Sin límite" : n}</option>
                  ))}
                </select>
              </div>

              {(
                [
                  ["show_soft_skills", "Mostrar habilidades blandas"],
                  ["show_courses", "Mostrar formación complementaria"],
                  ["show_languages", "Mostrar idiomas"],
                  ["show_links", "Mostrar enlaces (LinkedIn/GitHub/portafolio)"],
                  ["ai_rewrite_bullets", "Reformulación con IA (opt-in): reordena y enfatiza bullets por vacante, verificado término a término; si algo no cuadra se conserva el original"],
                ] as Array<[keyof PDFConfig, string]>
              ).map(([key, label]) => (
                <div className="field" style={{ display: "flex", alignItems: "flex-end" }} key={key}>
                  <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <input
                      type="checkbox"
                      checked={!!pdfConfig[key]}
                      onChange={e => handleUpdate({ [key]: e.target.checked } as PDFConfigUpdate)}
                    />
                    <span className="card-sub">{label}</span>
                  </label>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}