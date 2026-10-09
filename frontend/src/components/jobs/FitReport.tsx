import type { FitReport, FitSkillGroup } from "../../types/job";

function levelColor(level: string): string {
  switch (level) {
    case "muy_compatible":
      return "var(--success)";
    case "compatible":
      return "var(--success)";
    case "parcial":
      return "var(--warning, #b7791f)";
    case "poco_compatible":
      return "var(--danger)";
    default:
      return "var(--text-muted)";
  }
}

function CoverageBar({ value }: { value: number | null }) {
  if (value === null || value === undefined) {
    return <span className="chip chip-neutral">sin datos</span>;
  }
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span
        style={{
          display: "inline-block",
          width: 90,
          height: 8,
          borderRadius: 4,
          background: "var(--border)",
          overflow: "hidden",
        }}
      >
        <span
          style={{
            display: "block",
            width: `${Math.max(0, Math.min(100, value))}%`,
            height: "100%",
            background: "var(--success)",
          }}
        />
      </span>
      <strong>{value}%</strong>
    </span>
  );
}

function SkillGroup({
  title,
  group,
}: {
  title: string;
  group: FitSkillGroup;
}) {
  return (
    <div style={{ marginTop: 8 }}>
      <p style={{ margin: "0 0 4px", fontSize: 13 }}>
        <strong>{title}</strong> <CoverageBar value={group.coverage} />
      </p>
      {group.matched.length > 0 && (
        <div className="skill-chips">
          {group.matched.map((s) => (
            <span key={s} className="chip">
              {s} ✓
            </span>
          ))}
        </div>
      )}
      {group.missing.length > 0 && (
        <div className="skill-chips" style={{ marginTop: 4 }}>
          {group.missing.map((s) => (
            <span key={s} className="chip chip-missing">
              {s} ✕
            </span>
          ))}
        </div>
      )}
      {group.matched.length === 0 && group.missing.length === 0 && (
        <span className="chip chip-neutral">—</span>
      )}
    </div>
  );
}

/** Evaluación real oferta-vs-perfil por dimensiones (no solo el %). */
export function FitReportView({ report }: { report: FitReport }) {
  const dims = report.dimensions;
  return (
    <div style={{ marginTop: 12, borderTop: "1px solid var(--border)", paddingTop: 10 }}>
      <p style={{ fontSize: 13, margin: "0 0 4px" }}>
        Evaluación de tu perfil:{" "}
        <strong style={{ color: levelColor(report.level) }}>
          {report.label}
          {report.score !== null && report.score !== undefined
            ? ` (${Math.round(report.score)}%)`
            : ""}
        </strong>
      </p>
      {report.reasons.length > 0 && (
        <ul style={{ margin: "4px 0 4px 18px", padding: 0, fontSize: 13 }}>
          {report.reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
      <SkillGroup title="Técnicas" group={dims.tecnicas} />
      <SkillGroup title="Blandas" group={dims.blandas} />
      <div style={{ marginTop: 8 }}>
        <p style={{ margin: "0 0 4px", fontSize: 13 }}>
          <strong>Experiencia</strong>
        </p>
        <p className="card-sub" style={{ margin: 0 }}>
          {dims.experiencia.note}
          {dims.experiencia.profile_years !== null &&
            dims.experiencia.profile_years !== undefined &&
            ` (tienes ${dims.experiencia.profile_years} año(s))`}
        </p>
      </div>
      <div style={{ marginTop: 8 }}>
        <p style={{ margin: "0 0 4px", fontSize: 13 }}>
          <strong>Puesto</strong>
        </p>
        <p className="card-sub" style={{ margin: 0 }}>
          {dims.puesto.detected_role
            ? ` Detectado: ${dims.puesto.detected_role}. `
            : ""}
          {dims.puesto.note}
        </p>
      </div>
      {(report.strengths.length > 0 || report.gaps.length > 0) && (
        <div
          style={{
            display: "grid",
            gap: 8,
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            marginTop: 8,
          }}
        >
          {report.strengths.length > 0 && (
            <div>
              <p style={{ margin: "0 0 4px", fontSize: 13 }}>
                <strong>✅ Puntos fuertes</strong>
              </p>
              <ul style={{ margin: "0 0 0 18px", padding: 0, fontSize: 13 }}>
                {report.strengths.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}
          {report.gaps.length > 0 && (
            <div>
              <p style={{ margin: "0 0 4px", fontSize: 13 }}>
                <strong>⚠️ Brechas</strong>
              </p>
              <ul style={{ margin: "0 0 0 18px", padding: 0, fontSize: 13 }}>
                {report.gaps.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
