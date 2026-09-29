import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Header } from "../components/layout/Header";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { useJobs, useStats } from "../hooks/useApi";
import { STATUS_LABELS } from "../utils/constants";

const PIE_COLORS = ["#1f6feb", "#1a7f4b", "#9a6700", "#5b3df0", "#64707d"];

export function Analytics() {
  const jobs = useJobs();
  const stats = useStats();

  const all = useMemo(() => jobs.data ?? [], [jobs.data]);

  const byStatus = useMemo(
    () =>
      Object.entries(stats.data?.by_status ?? {}).map(([status, count]) => ({
        name: STATUS_LABELS[status as keyof typeof STATUS_LABELS] ?? status,
        value: count,
      })),
    [stats.data],
  );

  const bySource = useMemo(() => {
    const map = new Map<string, number>();
    for (const j of all) map.set(j.source, (map.get(j.source) ?? 0) + 1);
    return [...map.entries()].map(([name, value]) => ({ name, value }));
  }, [all]);

  const matchDist = useMemo(() => {
    const buckets = [
      { name: "0–39%", value: 0 },
      { name: "40–69%", value: 0 },
      { name: "70–100%", value: 0 },
    ];
    for (const j of all) {
      if (j.match_score === null) continue;
      if (j.match_score < 40) buckets[0].value += 1;
      else if (j.match_score < 70) buckets[1].value += 1;
      else buckets[2].value += 1;
    }
    return buckets;
  }, [all]);

  const loading = jobs.loading || stats.loading;
  const err = jobs.error ?? stats.error;

  return (
    <>
      <Header
        title="Análisis"
        subtitle="Estadísticas descriptivas de tus propios datos (sin rankings subjetivos)"
      />
      <div className="content">
        {loading ? (
          <LoadingState label="Calculando estadísticas…" />
        ) : err ? (
          <ErrorState
            message={err}
            onRetry={() => {
              jobs.reload();
              stats.reload();
            }}
          />
        ) : all.length === 0 ? (
          <EmptyState title="Sin datos para analizar." />
        ) : (
          <>
            <div className="grid-2" style={{ marginBottom: 16 }}>
              <div className="card">
                <h3 className="card-title">Ofertas por estado</h3>
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={byStatus} dataKey="value" nameKey="name" outerRadius={90} label>
                        {byStatus.map((_, i) => (
                          <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="card">
                <h3 className="card-title">Empresas más frecuentes</h3>
                <p className="card-sub">Top 10 real de tu base de datos</p>
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={stats.data?.top_companies ?? []}
                      layout="vertical"
                      margin={{ left: 90 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" allowDecimals={false} />
                      <YAxis type="category" dataKey="company" width={90} tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Bar dataKey="count" fill="#1f6feb" name="Ofertas" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="card">
                <h3 className="card-title">Ofertas por fuente</h3>
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={bySource} dataKey="value" nameKey="name" outerRadius={90} label>
                        {bySource.map((_, i) => (
                          <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="card">
                <h3 className="card-title">Distribución de coincidencia</h3>
                <p className="card-sub">
                  {(stats.data?.scored_count ?? 0) === 0
                    ? "Aún ninguna oferta analizada por el agente."
                    : `${stats.data?.scored_count} ofertas analizadas.`}
                </p>
                <div className="chart-box">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={matchDist}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="value" fill="#1a7f4b" name="Ofertas" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="card">
                <h3 className="card-title">Motivos de descarte</h3>
                <div className="chart-box">
                  {(stats.data?.discard_reasons.length ?? 0) === 0 ? (
                    <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                      Aún no hay descartes con motivo registrado.
                    </p>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={stats.data?.discard_reasons ?? []}
                        layout="vertical"
                        margin={{ left: 110 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" allowDecimals={false} />
                        <YAxis type="category" dataKey="reason" width={110} tick={{ fontSize: 11 }} />
                        <Tooltip />
                        <Bar dataKey="count" fill="#c0392b" name="Descartes" />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>

              <div className="card">
                <h3 className="card-title">Ofertas por modalidad</h3>
                <div className="notice-pending" style={{ marginTop: 10 }}>
                  <span>
                    Pendiente: el backend aún no persiste la modalidad como
                    campo estructurado (el scraper la ve en los tags del
                    detalle pero no la guarda). Cuando exista el campo, este
                    gráfico se alimentará solo.
                  </span>
                </div>
              </div>
            </div>

            <div className="card">
              <h3 className="card-title">Pendiente de datos del agente</h3>
              <p className="card-sub">
                Habilidades más solicitadas, habilidades faltantes frecuentes,
                coincidencia por cargo y categorías conservadas requieren que
                el agente escriba <code>match_score</code>,{" "}
                <code>matched_skills</code> y <code>missing_skills</code> en
                cada oferta. La interfaz ya está preparada para mostrarlos.
              </p>
            </div>
          </>
        )}
      </div>
    </>
  );
}
