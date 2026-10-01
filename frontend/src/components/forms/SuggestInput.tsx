import { useEffect, useId, useMemo, useRef, useState } from "react";

// Autocompletado con desplegable: filtra insensible a tildes/mayusculas
// ("bogota" encuentra "Bogotá"), muestra principales al abrir, permite
// texto libre y se navega con flechas + Enter + Escape.
function norm(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  placeholder?: string;
  title?: string;
  maxVisible?: number;
  disabled?: boolean;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  /**
   * Modo estricto: el valor debe coincidir con una opcion del catalogo
   * (insensible a tildes/mayusculas). Al salir del campo con texto que no
   * coincide, se revierte a vacio para evitar typos que devuelven
   * 0 resultados. Enter sin coincidencias no dispara busqueda.
   */
  strict?: boolean;
}

export function SuggestInput({
  value,
  onChange,
  options,
  placeholder,
  title,
  maxVisible = 8,
  disabled,
  onKeyDown,
  strict = false,
}: Props) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const filtered = useMemo(() => {
    const q = norm(value);
    const uniq = [...new Set(options.map((o) => o.trim()).filter(Boolean))];
    if (!q) return uniq.slice(0, maxVisible);
    const starts: string[] = [];
    const contains: string[] = [];
    for (const o of uniq) {
      const n = norm(o);
      if (n.startsWith(q)) starts.push(o);
      else if (n.includes(q)) contains.push(o);
    }
    return [...starts, ...contains].slice(0, maxVisible);
  }, [value, options, maxVisible]);

  useEffect(() => setHighlight(0), [filtered]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const pick = (v: string) => {
    onChange(v);
    setOpen(false);
  };

  const matchesOption = (v: string) => {
    const q = norm(v);
    if (!q) return true;
    return options.some((o) => norm(o) === q);
  };

  return (
    <div className="suggest" ref={boxRef}>
      <input
        className="input suggest-input"
        value={value}
        placeholder={placeholder}
        title={
          title ??
          (strict ? "Elige una opción de la lista para evitar errores" : undefined)
        }
        disabled={disabled}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          if (strict && value.trim() && !matchesOption(value)) {
            onChange("");
          }
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && open && filtered.length > 0) {
            e.preventDefault();
            setHighlight((h) => Math.min(h + 1, filtered.length - 1));
            return;
          }
          if (e.key === "ArrowUp" && open && filtered.length > 0) {
            e.preventDefault();
            setHighlight((h) => Math.max(h - 1, 0));
            return;
          }
          if (e.key === "Enter" && open && filtered.length > 0) {
            // Enter elige la sugerencia (no propaga: evita búsquedas
            // accidentales con el texto a medias).
            e.preventDefault();
            pick(filtered[highlight] ?? filtered[0]);
            return;
          }
          if (e.key === "Enter" && strict && open && filtered.length === 0) {
            // Estricto sin coincidencias: no buscar con un typo.
            e.preventDefault();
            setOpen(false);
            return;
          }
          if (e.key === "Escape") {
            setOpen(false);
            return;
          }
          onKeyDown?.(e);
        }}
      />
      {open && filtered.length > 0 && (
        <ul className="suggest-list" id={listId} role="listbox">
          {filtered.map((o, i) => (
            <li key={o} role="option" aria-selected={i === highlight}>
              <button
                type="button"
                className={i === highlight ? "active" : ""}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(o);
                }}
              >
                {o}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
