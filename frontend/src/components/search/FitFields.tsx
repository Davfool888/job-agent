import type { FitConfig, FitOptions } from "../../services/searchConfig";

interface Props {
  value: FitConfig;
  options: FitOptions | null;
  onChange: (patch: Partial<FitConfig>) => void;
  /** Etiqueta del valor vacio (ej. "Usar global" en perfiles). */
  emptyLabel?: string;
  disabled?: boolean;
}

/** Los 4 filtros de ajuste (nivel, experiencia, salario, contrato).
 * Se usan en Configuración (= global) y en cada perfil (= override).
 */
export function FitFields({ value, options, onChange, emptyLabel, disabled }: Props) {
  const none = emptyLabel ?? "Sin filtro";
  const toggleContract = (id: string) => {
    const current = value.contract_types ?? [];
    onChange({
      contract_types: current.includes(id)
        ? current.filter((c) => c !== id)
        : [...current, id],
    });
  };
  return (
    <div className="form-grid">
      <label>
        Nivel profesional
        <select
          className="select"
          value={value.seniority ?? ""}
          disabled={disabled}
          onChange={(e) => onChange({ seniority: e.target.value || null })}
          title="Descarta ofertas que pidan un nivel superior (se mira título y descripción)"
        >
          <option value="">{none}</option>
          {(options?.seniority_levels ?? []).map((l) => (
            <option key={l.id} value={l.id}>
              {l.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Tu experiencia
        <select
          className="select"
          value={value.experience_years ?? ""}
          disabled={disabled}
          onChange={(e) =>
            onChange({
              experience_years: e.target.value === "" ? null : Number(e.target.value),
            })
          }
          title="Descarta ofertas que exijan más años de los que tienes"
        >
          <option value="">{none}</option>
          {(options?.experience_buckets ?? []).map((b) => (
            <option key={b.years} value={b.years}>
              {b.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Salario mínimo
        <select
          className="select"
          value={value.salary_min_cop ?? ""}
          disabled={disabled}
          onChange={(e) =>
            onChange({
              salary_min_cop: e.target.value === "" ? null : Number(e.target.value),
            })
          }
          title="Descarta ofertas que paguen menos (solo si declaran salario)"
        >
          <option value="">{none}</option>
          {(options?.salary_min_options ?? []).map((b) => (
            <option key={b.min_cop} value={b.min_cop}>
              {b.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Salario máximo
        <select
          className="select"
          value={value.salary_max_cop ?? ""}
          disabled={disabled}
          onChange={(e) =>
            onChange({
              salary_max_cop: e.target.value === "" ? null : Number(e.target.value),
            })
          }
          title="Descarta ofertas que paguen más (solo si declaran salario)"
        >
          <option value="">{none}</option>
          {(options?.salary_max_options ?? []).map((b) => (
            <option key={b.max_cop} value={b.max_cop}>
              {b.label}
            </option>
          ))}
        </select>
      </label>
      <div>
        <p style={{ fontSize: 12.5, margin: "0 0 6px" }}>
          Contratos aceptados (vacío = todos)
        </p>
        {(options?.contract_types ?? []).map((c) => (
          <label
            key={c.id}
            style={{ display: "inline-flex", gap: 6, alignItems: "center", fontSize: 12.5, marginRight: 14 }}
          >
            <input
              type="checkbox"
              checked={(value.contract_types ?? []).includes(c.id)}
              disabled={disabled}
              onChange={() => toggleContract(c.id)}
            />
            {c.label}
          </label>
        ))}
      </div>
    </div>
  );
}
