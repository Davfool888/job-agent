import type { JobFilterState } from "../../types/filters";
import { DEFAULT_FILTERS } from "../../types/filters";

interface Props {
  value: JobFilterState;
  onChange: (f: JobFilterState) => void;
  companies: string[];
  locations: string[];
  sources: string[];
}

export function JobFilters({ value, onChange, companies, locations, sources }: Props) {
  const set = (patch: Partial<JobFilterState>) =>
    onChange({ ...value, ...patch });

  return (
    <div className="toolbar">
      <div className="toolbar-row">
        <input
          className="input search-input"
          placeholder="Buscar por cargo, empresa o palabra clave…"
          value={value.text}
          onChange={(e) => set({ text: e.target.value })}
        />
        <select
          className="select"
          value={value.sort}
          onChange={(e) =>
            set({ sort: e.target.value as JobFilterState["sort"] })
          }
          title="Ordenar"
        >
          <option value="recent">Más recientes</option>
          <option value="found">Recién encontradas</option>
          <option value="oldest">Más antiguas</option>
          <option value="match">Mayor coincidencia</option>
          <option value="company">Empresa (A–Z)</option>
          <option value="title">Cargo (A–Z)</option>
        </select>
      </div>
      <div className="toolbar-row">
        <select
          className="select"
          value={value.company}
          onChange={(e) => set({ company: e.target.value })}
        >
          <option value="">Todas las empresas</option>
          {companies.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select
          className="select"
          value={value.location}
          onChange={(e) => set({ location: e.target.value })}
        >
          <option value="">Todas las ubicaciones</option>
          {locations.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <select
          className="select"
          value={value.source}
          onChange={(e) => set({ source: e.target.value })}
        >
          <option value="">Todas las fuentes</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          className="select"
          value={String(value.minMatch)}
          onChange={(e) => set({ minMatch: Number(e.target.value) })}
          title="Coincidencia mínima (solo ofertas analizadas por el agente)"
        >
          <option value="0">Coincidencia: todas</option>
          <option value="40">≥ 40%</option>
          <option value="60">≥ 60%</option>
          <option value="80">≥ 80%</option>
        </select>
        <select
          className="select"
          value={String(value.maxAgeDays)}
          onChange={(e) => set({ maxAgeDays: Number(e.target.value) })}
          title="Antigüedad de la publicación (usa la fecha real de la fuente; si no la trae, la fecha en que se encontró)"
        >
          <option value="0">Publicadas: todas</option>
          <option value="1">Hoy</option>
          <option value="3">Últimos 3 días</option>
          <option value="7">Últimos 7 días</option>
          <option value="30">Últimos 30 días</option>
        </select>
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12.5 }}>
          <input
            type="checkbox"
            checked={value.onlyScored}
            onChange={(e) => set({ onlyScored: e.target.checked })}
          />
          Solo analizadas
        </label>
        <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12.5 }}>
          <input
            type="checkbox"
            checked={value.onlyReposted}
            onChange={(e) => set({ onlyReposted: e.target.checked })}
          />
          Solo republicadas
        </label>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => onChange(DEFAULT_FILTERS)}
        >
          Limpiar
        </button>
      </div>
    </div>
  );
}
