import { useEffect, useState } from "react";
import { Download, ExternalLink, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../jobs/States";
import {
  fetchProfileCv,
  fetchSearchProfiles,
  profileCvDownloadUrl,
} from "../../services/searchProfiles";
import type {
  ProfileCvStatus,
  SearchProfile,
} from "../../types/searchProfile";

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("es-CO", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatBytes(n: number | null | undefined): string {
  const bytes = n ?? 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

interface Row {
  profile: SearchProfile;
  cv: ProfileCvStatus;
}

/** Hojas de vida subidas como referencia en los perfiles de búsqueda.
 * Solo lectura + descarga: la gestión (subir/reemplazar/eliminar) vive
 * en la sección Búsqueda para no duplicar lógica.
 */
export function ProfileCvsTab({ disabled }: { disabled?: boolean }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const list = await fetchSearchProfiles();
        const cvs = await Promise.all(
          list.map((p) =>
            fetchProfileCv(p.id).catch(
              () => ({ profile_id: p.id, has_cv: false }) as ProfileCvStatus,
            ),
          ),
        );
        if (!alive) return;
        setRows(
          list
            .map((profile, i) => ({ profile, cv: cvs[i] }))
            .filter((r) => r.cv.has_cv),
        );
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Error");
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (disabled) {
    return (
      <p className="card-sub">
        Verifica tu sesión para ver las hojas de vida.
      </p>
    );
  }
  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />;
  if (!rows) return <LoadingState label="Cargando hojas de vida…" />;
  if (rows.length === 0) {
    return (
      <EmptyState
        title="Sin hojas de vida."
        hint="Sube un PDF como referencia desde la sección Búsqueda (cada perfil de búsqueda) y aparecerá aquí."
      />
    );
  }
  return (
    <div className="job-list">
      {rows.map(({ profile, cv }) => (
        <div key={profile.id} className="job-card">
          <div className="job-card-top">
            <div className="job-card-main">
              <h3 className="job-title">
                <FileText size={14} /> {cv.filename ?? "Hoja de vida"}
              </h3>
              <div className="job-meta">
                <span>Perfil: {profile.name}</span>
                <span>{cv.pages ?? 0} pág.</span>
                <span>{formatBytes(cv.size_bytes)}</span>
                <span>Subida: {formatDateTime(cv.uploaded_at ?? null)}</span>
              </div>
              {(cv.chars ?? 0) === 0 && (
                <p className="card-sub" style={{ margin: "4px 0 0" }}>
                  Este PDF no trae texto extraíble (¿escaneado?).
                </p>
              )}
            </div>
          </div>
          <div className="job-card-foot">
            <a
              className="btn btn-ghost btn-sm"
              href={profileCvDownloadUrl(profile.id)}
            >
              <Download size={14} /> Descargar
            </a>
            <a
              className="btn btn-ghost btn-sm"
              href={profileCvDownloadUrl(profile.id)}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={14} /> Abrir
            </a>
            <span className="spacer" />
            <Link className="btn btn-ghost btn-sm" to="/search">
              Gestionar en Búsqueda
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}
