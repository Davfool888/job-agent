import { useEffect, useState } from "react";
import { Header } from "../components/layout/Header";
import {
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { SimpleProfileTab } from "../components/profile/SimpleProfileTab";
import { StructuredProfileManager } from "../components/profile/StructuredProfileManager";
import { useAuth } from "../context/AuthContext";
import { useProfile } from "../hooks/useApi";
import { ADMIN_EMAIL } from "../lib/firebase";
import { fetchCatalogs } from "../services/profile";
import { canonicalLocation } from "../utils/profileOptions";
import type {
  Catalogs,
  LanguageEntry,
  Profile,
  ProfileEntry,
} from "../types/profile";
import { EMPTY_PROFILE } from "../types/profile";

function useIsAdminSession(): boolean {
  const { firebaseUser, isGuest } = useAuth();
  if (!firebaseUser || isGuest) return false;
  return (firebaseUser.email ?? "").trim().toLowerCase() === ADMIN_EMAIL;
}

function useCatalogs() {
  const [catalogs, setCatalogs] = useState<Catalogs | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fetchCatalogs()
      .then((c: Catalogs) => alive && setCatalogs(c))
      .catch((e: unknown) =>
        alive && setError(e instanceof Error ? e.message : "Error"),
      );
    return () => {
      alive = false;
    };
  }, []);
  return { catalogs, error };
}

export function ProfilePage() {
  const { data, loading, error, reload, save, saving } = useProfile();
  const { catalogs } = useCatalogs();
  const { firebaseUser } = useAuth();
  const isAdmin = useIsAdminSession();
  const [form, setForm] = useState<Profile | null>(null);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const initialExperiences = (data as any)?.experiences || [];
  const initialEducation = (data as any)?.education || [];
  const initialLanguages = (data as any)?.languages || [];

  const [simpleExperiences, setSimpleExperiences] = useState<ProfileEntry[]>(() => initialExperiences);
  const [simpleEducation, setSimpleEducation] = useState<ProfileEntry[]>(() => initialEducation);
  const [simpleLanguages, setSimpleLanguages] = useState<LanguageEntry[]>(() => initialLanguages);

  if (loading) {
    return (
      <>
        <Header title="Perfil profesional" />
        <div className="content">
          <LoadingState label="Cargando perfil…" />
        </div>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <Header title="Perfil profesional" />
        <div className="content">
          <ErrorState message={error ?? "Error"} onRetry={reload} />
        </div>
      </>
    );
  }

  const locked =
    !!data &&
    !!firebaseUser &&
    !isAdmin &&
    data.scope !== "own" &&
    data.scope !== "demo";
  const current = locked ? { ...EMPTY_PROFILE } : (form ?? data);

  const titleOptions =
    catalogs?.professional_titles.map((t) => t.label) ?? [];
  const cityOptions = catalogs?.cities.map((c) => c.label) ?? [];
  const locationValue = canonicalLocation(current.location, cityOptions);

  const citySelectOptions = (value: string) =>
    value && !cityOptions.includes(value)
      ? [...cityOptions, value]
      : cityOptions;

  const set = (patch: Partial<Profile>) => {
    if (locked) return;
    setForm({ ...current, ...patch });
    setSaved(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (locked) {
      setSaveError("Sesión sin acceso a este perfil.");
      return;
    }
    setSaveError(null);
    try {
      const updated = await save(current);
      setForm(updated);
      setSaved(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Error inesperado");
    } finally {
      // noop
    }
  };

  const [activeTab, setActiveTab] = useState<"simple" | "structured">("simple");

  return (
    <>
      <Header
        title="Perfil profesional"
        subtitle="Fuente estructurada para matching, CV y análisis (PUT /profile y /profile/full)"
      />
      <div className="content">
        {locked && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>
              🔒 Esta sesión no tiene acceso al perfil mostrado por el
              servidor. No se muestra ni se puede editar nada hasta
              verificar la sesión.
            </p>
          </div>
        )}
        {data.scope === "own" && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>
              👤 Este es <strong>tu perfil personal</strong>: empieza en
              blanco y solo se llena con lo que guardes aquí. El perfil
              base de la cuenta principal no es visible para ti.
            </p>
          </div>
        )}
        {data.scope === "demo" && (
          <div className="card" style={{ marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>
              🧪 Estás viendo <strong>datos de prueba</strong> del modo
              invitado. Puedes editarlos libremente para testear; no
              afectan al perfil real.
            </p>
          </div>
        )}

        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)", marginBottom: 16 }}>
            <button
              type="button"
              className={`btn btn-sm ${activeTab === "simple" ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setActiveTab("simple")}
              disabled={locked}
              style={{ padding: "8px 16px" }}
            >
              Perfil Simple
            </button>
            <button
              type="button"
              className={`btn btn-sm ${activeTab === "structured" ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setActiveTab("structured")}
              disabled={locked}
              style={{ padding: "8px 16px" }}
            >
              Perfil Estructurado
            </button>
          </div>
          <p className="card-sub" style={{ marginBottom: 0 }}>
            {activeTab === "simple"
              ? "Información básica de contacto, experiencia laboral, educación e idiomas (descripción general)."
              : "Perspectivas detalladas por experiencia/educación: tareas específicas, habilidades y herramientas por óptica (Data Analytics, Software, Finanzas, etc.)."}
          </p>
        </div>

        {activeTab === "simple" && (
          <SimpleProfileTab
            locked={locked}
            current={current}
            set={set}
            saved={saved}
            saveError={saveError}
            submit={submit}
            saving={saving}
            titleOptions={titleOptions}
            citySelectOptions={citySelectOptions}
            locationValue={locationValue}
            experiences={simpleExperiences}
            setExperiences={setSimpleExperiences}
            education={simpleEducation}
            setEducation={setSimpleEducation}
            languages={simpleLanguages}
            setLanguages={setSimpleLanguages}
          />
        )}

        {activeTab === "structured" && (
          <StructuredProfileManager
            locked={locked}
            simpleExperiences={simpleExperiences}
            simpleEducation={simpleEducation}
            simpleLanguages={simpleLanguages}
          />
        )}
      </div>
    </>
  );
}