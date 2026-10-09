import { useEffect, useState } from "react";
import { Header } from "../components/layout/Header";
import {
  ErrorState,
  LoadingState,
} from "../components/jobs/States";
import { SimpleProfileTab } from "../components/profile/SimpleProfileTab";
import { StructuredProfileManager } from "../components/profile/StructuredProfileManager";
import { ProfileCvsTab } from "../components/profile/ProfileCvsTab";
import { useAuth } from "../context/AuthContext";
import { useProfile } from "../hooks/useApi";
import { ADMIN_EMAIL } from "../lib/firebase";
import { fetchCatalogs, fetchFullProfile, importPdfApply, importPdfPreview, saveFullProfile } from "../services/profile";
import type { PdfImportResult } from "../services/profile";
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
  // Todos los hooks SIEMPRE antes de cualquier return temprano: si un
  // useState queda despues de `if (loading) return ...`, React lanza el
  // error #310 (mas hooks que en el render anterior) al terminar la carga.
  const [form, setForm] = useState<Profile | null>(null);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [simpleExperiences, setSimpleExperiences] = useState<ProfileEntry[]>([]);
  const [simpleEducation, setSimpleEducation] = useState<ProfileEntry[]>([]);
  const [simpleLanguages, setSimpleLanguages] = useState<LanguageEntry[]>([]);
  const [hydratedFor, setHydratedFor] = useState<string | null>(null);
  const [listsHydrated, setListsHydrated] = useState(false);
  const [activeTab, setActiveTab] = useState<"simple" | "structured" | "cvs">("simple");
  // Se incrementa al guardar el tab simple: el estructurado se
  // refresca solo si no tiene ediciones pendientes.
  const [simpleRevision, setSimpleRevision] = useState(0);

  // Tras guardar el estructurado: lo simple refleja lo guardado
  // (listas + plano recargado del backend, ya sincronizado).
  const handleStructuredSaved = (sections: {
    experience: ProfileEntry[];
    education: ProfileEntry[];
    languages: LanguageEntry[];
  }) => {
    setSimpleExperiences(sections.experience);
    setSimpleEducation(sections.education);
    setSimpleLanguages(sections.languages);
    setForm(null);
    setSaved(false);
    void reload();
  };
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<PdfImportResult | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);

  const runPdfPreview = async (file: File) => {
    setImportFile(file);
    setImportError(null);
    setImportPreview(null);
    setImportLoading(true);
    try {
      setImportPreview(await importPdfPreview(file));
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "No se pudo leer el PDF.");
    } finally {
      setImportLoading(false);
    }
  };

  const runPdfApply = async () => {
    if (!importFile || locked) return;
    setImportError(null);
    setImportLoading(true);
    try {
      const result = await importPdfApply(importFile);
      setImportPreview(result);
      // Refresca el formulario y las listas desde lo guardado.
      const rich = await fetchFullProfile().catch(() => null);
      if (rich) {
        setSimpleExperiences(((rich.experience || []) as ProfileEntry[]));
        setSimpleEducation(((rich.education || []) as ProfileEntry[]));
        setSimpleLanguages(((rich.languages || []) as LanguageEntry[]));
      }
      setForm(null);
      setHydratedFor(null);
      setListsHydrated(false);
      reload();
      setSaved(true);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "No se pudo aplicar el perfil.");
    } finally {
      setImportLoading(false);
    }
  };

  // Hidrata los estados editables cuando llega data (los inicializadores
  // de useState solo corren en el primer render, con data=null).
  // Las listas (experiencia/educación/idiomas) viven en el perfil
  // estructurado: se cargan de /profile/full una sola vez y solo si el
  // usuario aún no editó nada (no se pisa lo que ya escribió).
  const dataKey = data ? JSON.stringify({
    e: (data as any)?.experiences ?? [],
    d: (data as any)?.education ?? [],
    l: (data as any)?.languages ?? [],
  }) : null;
  useEffect(() => {
    if (!data || !dataKey || hydratedFor === dataKey) return;
    setHydratedFor(dataKey);
    setForm(null);
    setSaved(false);
    setSimpleExperiences(((data as any)?.experiences || []) as ProfileEntry[]);
    setSimpleEducation(((data as any)?.education || []) as ProfileEntry[]);
    setSimpleLanguages(((data as any)?.languages || []) as LanguageEntry[]);
  }, [data, dataKey, hydratedFor]);
  useEffect(() => {
    if (!data || listsHydrated) return;
    let alive = true;
    fetchFullProfile()
      .then((rich) => {
        if (!alive) return;
        setSimpleExperiences((prev) =>
          prev.length > 0 ? prev : ((rich.experience || []) as ProfileEntry[]));
        setSimpleEducation((prev) =>
          prev.length > 0 ? prev : ((rich.education || []) as ProfileEntry[]));
        setSimpleLanguages((prev) =>
          prev.length > 0 ? prev : ((rich.languages || []) as LanguageEntry[]));
        setListsHydrated(true);
      })
      .catch(() => alive && setListsHydrated(true));
    return () => {
      alive = false;
    };
  }, [data, listsHydrated]);

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
      // 1. Guarda el plano (nombre, contacto, ubicación...).
      const updated = await save(current);
      setForm(updated);
      // 2. Persiste las listas del tab simple en el estructurado.
      // Merge por id: conserva las perspectivas ya creadas y propaga
      // los eliminados. Sin esto, experiencias/idiomas se perdían al
      // recargar (el plano no tiene esas claves).
      const mergeSection = <T extends { id?: string }>(
        simple: T[],
        stored: T[] | undefined,
      ): T[] => {
        const prev = new Map(
          (stored ?? []).map((item) => [item.id, item]),
        );
        return simple.map((item) => {
          const old = item.id ? prev.get(item.id) : undefined;
          if (!old) return item;
          const { perspectives, ...rest } = item as unknown as Record<string, unknown>;
          return {
            ...rest,
            perspectives:
              (old as unknown as Record<string, unknown>).perspectives ?? perspectives ?? [],
          } as unknown as T;
        });
      };
      const rich = await fetchFullProfile().catch(() => null);
      await saveFullProfile({
        experience: mergeSection(simpleExperiences, rich?.experience as ProfileEntry[] | undefined),
        education: mergeSection(simpleEducation, rich?.education as ProfileEntry[] | undefined),
        languages: mergeSection(simpleLanguages, rich?.languages as LanguageEntry[] | undefined),
      });
      setSaved(true);
      setSimpleRevision((r) => r + 1);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Error inesperado");
    } finally {
      // noop
    }
  };

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
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <div>
              <strong>Subir currículum</strong>
              <p className="card-sub" style={{ margin: "4px 0 0" }}>
                Escanea tu PDF y precarga el perfil. Revisa la vista previa antes de aplicar.
              </p>
            </div>
            <label className="btn btn-sm btn-primary" style={{ marginLeft: "auto", cursor: "pointer" }}>
              {importLoading ? "Leyendo…" : "Subir currículum"}
              <input
                type="file"
                accept="application/pdf,.pdf"
                hidden
                disabled={locked || importLoading}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (f) void runPdfPreview(f);
                }}
              />
            </label>
          </div>
          {importError && (
            <p style={{ color: "var(--danger, #c00)", fontSize: 13 }}>⚠ {importError}</p>
          )}
          {importPreview && (
            <div style={{ marginTop: 12, fontSize: 13 }}>
              <p style={{ margin: "0 0 8px" }}>
                📄 <strong>{importPreview.filename || importFile?.name}</strong>
                {importPreview.applied ? " — aplicado al perfil ✅" : " — vista previa (sin guardar)"}
              </p>
              <ul style={{ margin: "0 0 8px 18px", padding: 0 }}>
                <li>Experiencia: {importPreview.profile.experience?.length ?? 0}</li>
                <li>Educación formal: {importPreview.profile.education?.length ?? 0}</li>
                <li>Cursos: {importPreview.profile.certifications?.length ?? 0}</li>
                <li>Idiomas: {importPreview.profile.languages?.length ?? 0}</li>
                <li>Proyectos: {importPreview.profile.projects?.length ?? 0}</li>
              </ul>
              {importPreview.warnings.length > 0 && (
                <details style={{ marginBottom: 8 }}>
                  <summary>Avisos ({importPreview.warnings.length})</summary>
                  <ul style={{ margin: "8px 0 0 18px", padding: 0 }}>
                    {importPreview.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </details>
              )}
              {!importPreview.applied && (
                <button
                  type="button"
                  className="btn btn-sm btn-primary"
                  disabled={locked || importLoading}
                  onClick={() => void runPdfApply()}
                >
                  Aplicar al perfil
                </button>
              )}
            </div>
          )}
        </div>

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
            <button
              type="button"
              className={`btn btn-sm ${activeTab === "cvs" ? "btn-primary" : "btn-ghost"}`}
              onClick={() => setActiveTab("cvs")}
              disabled={locked}
              style={{ padding: "8px 16px" }}
            >
              Hojas de vida
            </button>
          </div>
          <p className="card-sub" style={{ marginBottom: 0 }}>
            {activeTab === "simple"
              ? "Información básica de contacto, experiencia laboral, educación e idiomas (descripción general). Lo que guardes aquí aparece también en el estructurado."
              : activeTab === "structured"
                ? "Todo editable con guardado: lo que guardes aquí aparece también en el simple. Se carga solo al abrir esta pestaña."
                : "PDFs subidos como referencia en tus perfiles de búsqueda (solo lectura y descarga)."}
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
            externalRevision={simpleRevision}
            onSaved={handleStructuredSaved}
          />
        )}

        {activeTab === "cvs" && <ProfileCvsTab disabled={locked} />}
      </div>
    </>
  );
}