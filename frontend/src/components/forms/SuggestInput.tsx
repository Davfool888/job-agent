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

  return (
    <div className="suggest" ref={boxRef}>
      <input
        className="input suggest-input"
        value={value}
        placeholder={placeholder}
        title={title}
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
