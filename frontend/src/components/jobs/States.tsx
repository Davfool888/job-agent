import { Inbox, TriangleAlert } from "lucide-react";

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="state-box">
      <Inbox />
      <h3>{title}</h3>
      {hint && <p>{hint}</p>}
      {action}
    </div>
  );
}

export function LoadingState({ label = "Cargando…" }: { label?: string }) {
  return (
    <div className="state-box">
      <h3>{label}</h3>
      <p>Consultando al backend…</p>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="alert-error">
      <p style={{ margin: 0, display: "flex", gap: 8, alignItems: "center" }}>
        <TriangleAlert size={16} /> {message}
      </p>
      {onRetry && (
        <button
          className="btn btn-ghost btn-sm"
          style={{ marginTop: 10 }}
          onClick={onRetry}
        >
          Reintentar
        </button>
      )}
    </div>
  );
}
