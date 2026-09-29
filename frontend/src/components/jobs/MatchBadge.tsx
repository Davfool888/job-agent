import { Target } from "lucide-react";

// El porcentaje SIEMPRE viene del backend (Job.match_score).
// `null` = el agente aun no analizo la oferta: se muestra
// "Sin analizar", nunca un numero inventado.
export function MatchBadge({ score }: { score: number | null }) {
  if (score === null || score === undefined) {
    return (
      <span className="badge badge-match-none" title="Pendiente de análisis del agente">
        <Target /> Sin analizar
      </span>
    );
  }
  const cls =
    score >= 70 ? "badge-match" : score >= 40 ? "badge-match-mid" : "badge-match-none";
  return (
    <span className={`badge ${cls}`}>
      <Target /> {Math.round(score)}%
    </span>
  );
}
