import { useEffect, useState } from "react";
import { Header } from "../components/layout/Header";
import { API_URL } from "../services/api";
import { checkHealth } from "../services/jobs";
import { useTheme, type Theme } from "../hooks/useTheme";
import { fetchPDFConfig, updatePDFConfig, resetPDFConfig, type PDFConfig, type PDFConfigUpdate } from "../services/pdfConfig";

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
  const available = AVAILABLE_SECTIONS.filter(s => !value.includes(s.slug));
  return (
    <div className="field">
      <label>Orden de secciones</label>
      <p className="card-sub" style={{ marginBottom: 8 }}>
        Arrastra para reordenar. Secciones disponibles:
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {value.map((slug, idx) => {
          const section = AVAILABLE_SECTIONS.find(s => s.slug === slug);
          if (!section) return null;
          return (
            <div key={slug} className="card" style={{ display: "flex", alignItems: "center", gap: 8, padding: 8 }}>
              <span style={{ cursor: "grab", fontSize: 18 }}>⋮⋮</span>
              <span style={{ flex: 1 }}>{section.label}</span>
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

              <NumberInput
                label="Tamaño de fuente (pt)"
                value={pdfConfig.font_size_pt}
                onChange={v => handleUpdate({ font_size_pt: v })}
                min={8}
                max={16}
                step={1}
                suffix="pt"
              />

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

              {/* Color acento */}
              <div className="field">
                <label>Color acento</label>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <input
                    type="color"
                    value={pdfConfig.accent_color}
                    onChange={e => handleUpdate({ accent_color: e.target.value })}
                    style={{ width: 50, height: 36, border: "none", borderRadius: 4, cursor: "pointer" }}
                  />
                  <input
                    type="text"
                    className="select"
                    value={pdfConfig.accent_color}
                    onChange={e => handleUpdate({ accent_color: e.target.value })}
                    style={{ maxWidth: 120, fontFamily: "monospace" }}
                    placeholder="#2c3e50"
                  />
                </div>
              </div>

              {/* Márgenes */}
              <div className="field">
                <label>Márgenes (mm)</label>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
                  <NumberInput label="Superior" value={pdfConfig.margin_top_mm} onChange={v => handleUpdate({ margin_top_mm: v })} min={10} max={40} suffix="mm" />
                  <NumberInput label="Inferior" value={pdfConfig.margin_bottom_mm} onChange={v => handleUpdate({ margin_bottom_mm: v })} min={10} max={40} suffix="mm" />
                  <NumberInput label="Izquierdo" value={pdfConfig.margin_left_mm} onChange={v => handleUpdate({ margin_left_mm: v })} min={10} max={40} suffix="mm" />
                  <NumberInput label="Derecho" value={pdfConfig.margin_right_mm} onChange={v => handleUpdate({ margin_right_mm: v })} min={10} max={40} suffix="mm" />
                </div>
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

              {/* Chips de skills */}
              <div className="field" style={{ display: "flex", alignItems: "flex-end" }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <input
                    type="checkbox"
                    checked={pdfConfig.show_skill_chips}
                    onChange={e => handleUpdate({ show_skill_chips: e.target.checked })}
                  />
                  <span className="card-sub">Mostrar chips de skills en Competencias Técnicas</span>
                </label>
              </div>

              {/* Modo compacto */}
              <div className="field" style={{ display: "flex", alignItems: "flex-end" }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <input
                    type="checkbox"
                    checked={pdfConfig.compact_mode}
                    onChange={e => handleUpdate({ compact_mode: e.target.checked })}
                  />
                  <span className="card-sub">Modo compacto (menos espaciado general)</span>
                </label>
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

              {/* Orden de secciones */}
              <SectionOrderEditor
                value={pdfConfig.section_order}
                onChange={v => handleUpdate({ section_order: v })}
              />
            </div>
          </div>
        )}

        <div className="card">
          <h3 className="card-title">Estado de la conexión</h3>
          <p className="card-sub">
            La autenticación se gestiona via Firebase (Google). Si el backend
            no tiene credenciales, funciona en modo local sin autenticación.
          </p>
          <button className="btn btn-ghost btn-sm" onClick={ping} disabled={checking}>
            {checking ? "Comprobando…" : "Probar backend"}
          </button>
          <span style={{ marginLeft: 10, fontSize: 13 }}>{health}</span>
        </div>
      </div>
    </>
  );
}