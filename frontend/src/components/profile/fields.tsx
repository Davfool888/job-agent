import { useMemo, useState } from "react";

// Autocomplete sobre catalogo: escribe para filtrar, elige opcion.
// Guarda el id; si no coincide nada, permite "Otro"/texto segun props.
export function Autocomplete({
  value,
  onChange,
  options,
  placeholder,
  allowCustom = false,
  customLabel = "Otro",
  disabled = false,
}: {
  value: string;
  onChange: (id: string) => void;
  options: Array<{ id: string; label: string; hint?: string }>;
  placeholder?: string;
  allowCustom?: boolean;
  customLabel?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const selected = options.find((o) => o.id === value);

  const filtered = useMemo(() => {
    const q = text.trim().toLowerCase();
    const list = q
      ? options.filter((o) => o.label.toLowerCase().includes(q))
      : options;
    return list.slice(0, 12);
  }, [options, text]);

  return (
    <div style={{ position: "relative" }}>
      <input
        className="input"
        style={{ width: "100%" }}
        value={open ? text : (selected?.label ?? value)}
        placeholder={placeholder}
        disabled={disabled}
        onFocus={() => {
          if (!disabled) {
            setText("");
            setOpen(true);
          }
        }}
        onChange={(e) => {
          if (!disabled) {
            setText(e.target.value);
            setOpen(true);
            if (e.target.value === "") onChange("");
          }
        }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && (
        <div
          style={{
            position: "absolute",
            zIndex: 20,
            left: 0,
            right: 0,
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            marginTop: 4,
            maxHeight: 220,
            overflowY: "auto",
            boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
          }}
        >
          {filtered.map((o) => (
            <button
              key={o.id}
              type="button"
              className="btn btn-ghost btn-sm"
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                border: "none",
                borderRadius: 0,
              }}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onChange(o.id);
                setOpen(false);
              }}
            >
              {o.label}
              {o.hint && (
                <span style={{ color: "var(--text-muted)" }}> — {o.hint}</span>
              )}
            </button>
          ))}
          {allowCustom && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ display: "block", width: "100%", textAlign: "left" }}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onChange("other");
                setOpen(false);
              }}
            >
              {customLabel}
            </button>
          )}
          {filtered.length === 0 && !allowCustom && (
            <p style={{ padding: "8px 12px", fontSize: 12.5, margin: 0 }}>
              Sin coincidencias.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// Fecha como date picker nativo (YYYY-MM-DD). month=true -> solo mes.
// Reconoce lo que deja la extracción del CV (ISO, MM/YYYY, DD/MM/YYYY,
// YYYY, "Mar 2025"/"marzo 2025") y lo convierte al formato del input;
// lo irreconocible se muestra vacío en vez de romper el picker.
const MONTHS: Record<string, string> = {
  ene: "01", enero: "01", jan: "01", january: "01",
  feb: "02", febrero: "02", febr: "02", february: "02",
  mar: "03", marzo: "03", march: "03",
  abr: "04", abril: "04", apr: "04", april: "04",
  may: "05", mayo: "05",
  jun: "06", junio: "06", june: "06",
  jul: "07", julio: "07", july: "07",
  ago: "08", agosto: "08", aug: "08", august: "08",
  sep: "09", sept: "09", set: "09", septiembre: "09", september: "09",
  oct: "10", octubre: "10", october: "10",
  nov: "11", noviembre: "11", november: "11",
  dic: "12", diciembre: "12", dec: "12", december: "12",
};

function normText(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

export function toDateInputValue(
  value: string | null | undefined,
  month = false,
): string {
  const raw = (value ?? "").trim();
  if (!raw) return "";
  // Ya ISO: YYYY-MM-DD[...] o YYYY-MM.
  let m = raw.match(/^(\d{4})-(\d{2})(?:-(\d{2}))?/);
  if (m) {
    const day = m[3] ?? "01";
    if (month) return `${m[1]}-${m[2]}`;
    return m[3] ? `${m[1]}-${m[2]}-${day}` : `${m[1]}-${m[2]}-01`;
  }
  // MM/YYYY o MM-YYYY.
  m = raw.match(/^(\d{1,2})[/-](\d{4})$/);
  if (m) {
    const mm = m[1].padStart(2, "0");
    if (Number(mm) < 1 || Number(mm) > 12) return "";
    return month ? `${m[2]}-${mm}` : `${m[2]}-${mm}-01`;
  }
  // DD/MM/YYYY o DD-MM-YYYY.
  m = raw.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
  if (m) {
    const dd = m[1].padStart(2, "0");
    const mm = m[2].padStart(2, "0");
    if (Number(mm) < 1 || Number(mm) > 12 || Number(dd) < 1 || Number(dd) > 31)
      return "";
    return month ? `${m[3]}-${mm}` : `${m[3]}-${mm}-${dd}`;
  }
  // Solo año.
  m = raw.match(/^(\d{4})$/);
  if (m) return month ? `${m[1]}-01` : `${m[1]}-01-01`;
  // "Mar 2025" / "marzo 2025" (ES+EN, con o sin tildes).
  m = normText(raw).match(/^([a-z]+)\s+(\d{4})$/);
  if (m) {
    const mm = MONTHS[m[1]];
    if (!mm) return "";
    return month ? `${m[2]}-${mm}` : `${m[2]}-${mm}-01`;
  }
  return "";
}

export function DateInput({
  value,
  onChange,
  month = false,
  disabled = false,
}: {
  value: string | null | undefined;
  onChange: (iso: string | null) => void;
  month?: boolean;
  disabled?: boolean;
}) {
  const shown = toDateInputValue(value, month);
  return (
    <input
      className="input"
      type={month ? "month" : "date"}
      value={shown}
      disabled={disabled}
      onChange={(e) => {
        if (disabled) return;
        const raw = e.target.value;
        if (!raw) {
          onChange(null);
          return;
        }
        onChange(month ? `${raw}-01` : raw);
      }}
    />
  );
}

// Lista de tags con agregar/eliminar (skills, dominios, etc.).
// Con `suggestions` muestra desplegable al escribir (vocabulario guiado
// pero abierto: permite texto libre con `allowCustom`).
export function TagInput({
  value,
  onChange,
  placeholder,
  suggestions = [],
  allowCustom = true,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  suggestions?: string[];
  allowCustom?: boolean;
}) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const add = (raw?: string) => {
    const item = (raw ?? text).trim();
    if (item && !value.includes(item)) onChange([...value, item]);
    setText("");
    setOpen(false);
  };
  const norm = (s: string) =>
    s
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .trim();
  const trimmedText = text.trim();
  const exactMatch =
    trimmedText !== "" &&
    [...value, ...suggestions].some((s) => norm(s) === norm(trimmedText));
  const filtered = useMemo(() => {
    const seen = new Set(value);
    const uniq = [...new Set(suggestions.map((s) => s.trim()).filter(Boolean))].filter(
      (s) => !seen.has(s),
    );
    const q = norm(text);
    if (!q) return uniq.slice(0, 8);
    const starts: string[] = [];
    const contains: string[] = [];
    for (const s of uniq) {
      const n = norm(s);
      if (n.startsWith(q)) starts.push(s);
      else if (n.includes(q)) contains.push(s);
    }
    return [...starts, ...contains].slice(0, 8);
  }, [suggestions, text, value]);
  const showList = open && (filtered.length > 0 || (allowCustom && trimmedText !== ""));
  return (
    <div>
      <div className="skill-chips" style={{ marginBottom: 6 }}>
        {value.map((item) => (
          <span key={item} className="chip">
            {item}{" "}
            <button
              type="button"
              aria-label={`Quitar ${item}`}
              onClick={() => onChange(value.filter((v) => v !== item))}
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "inherit",
                padding: 0,
              }}
            >
              ✕
            </button>
          </span>
        ))}
        {value.length === 0 && (
          <span className="chip chip-neutral">—</span>
        )}
      </div>
      <div style={{ display: "flex", gap: 6, position: "relative" }}>
        <input
          className="input"
          style={{ flex: 1 }}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              if (filtered.length > 0) add(filtered[0]);
              else if (allowCustom) add();
            }
            if (e.key === "Escape") setOpen(false);
          }}
          placeholder={placeholder ?? "Agregar y Enter"}
        />
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => add()}>
          +
        </button>
        {showList && (
          <div
            style={{
              position: "absolute",
              zIndex: 20,
              top: "100%",
              left: 0,
              right: 40,
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              marginTop: 4,
              maxHeight: 200,
              overflowY: "auto",
              boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
            }}
          >
            {filtered.map((s) => (
              <button
                key={s}
                type="button"
                className="btn btn-ghost btn-sm"
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  border: "none",
                  borderRadius: 0,
                }}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => add(s)}
              >
                {s}
              </button>
            ))}
            {allowCustom && trimmedText !== "" && !exactMatch && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  border: "none",
                  borderRadius: 0,
                  fontStyle: "italic",
                }}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => add()}
              >
                ➕ Agregar “{trimmedText}”
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Tarjeta colapsable reutilizable para entradas (experiencia, estudios...).
export function EntryCard({
  title,
  subtitle,
  badge,
  onRemove,
  children,
  defaultOpen = false,
}: {
  title: string;
  subtitle?: string;
  badge?: string;
  onRemove?: () => void;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: 12,
        marginBottom: 10,
      }}
    >
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <strong
          style={{ flex: 1, cursor: "pointer" }}
          onClick={() => setOpen((o) => !o)}
        >
          {title || "Nueva entrada"}
          {subtitle ? ` — ${subtitle}` : ""}
        </strong>
        {badge && <span className="card-sub">{badge}</span>}
        {onRemove && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
          >
            Eliminar
          </button>
        )}
      </div>
      {open && <div style={{ marginTop: 10 }}>{children}</div>}
    </div>
  );
}
