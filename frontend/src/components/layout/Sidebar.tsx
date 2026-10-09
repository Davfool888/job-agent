import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import {
  ArrowLeftRight,
  BarChart3,
  BookmarkX,
  Briefcase,
  ChevronUp,
  Eye,
  FileText,
  Layers,
  LayoutDashboard,
  LogOut,
  Menu,
  Radar,
  Send,
  Settings,
  User,
} from "lucide-react";
import { API_URL } from "../../services/api";
import { useAuth } from "../../context/AuthContext";

const LINKS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/jobs", label: "Ofertas", icon: Briefcase },
  { to: "/slices", label: "Slices", icon: Layers },
  { to: "/search", label: "Búsqueda", icon: Radar },
  { to: "/discarded", label: "Descartadas", icon: BookmarkX },
  { to: "/viewed", label: "Vistas", icon: Eye },
  { to: "/applications", label: "Postulaciones", icon: Send },
  { to: "/cv", label: "Guardadas", icon: FileText },
  { to: "/analytics", label: "Análisis", icon: BarChart3 },
  { to: "/profile", label: "Perfil", icon: User },
  { to: "/settings", label: "Configuración", icon: Settings },
];

export function Sidebar() {
  const [open, setOpen] = useState(false);
  const { configured, firebaseUser, isGuest, profile, logout, switchAccount } =
    useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [menuError, setMenuError] = useState<string | null>(null);

  const displayName = isGuest
    ? "Invitado"
    : profile?.nombre || firebaseUser?.displayName || "Usuario";
  const email = isGuest ? "" : profile?.email || firebaseUser?.email || "";
  const photo = firebaseUser?.photoURL ?? null;
  const initials = displayName
    .trim()
    .split(/\s+/)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const doLogout = async () => {
    setBusy(true);
    setMenuError(null);
    try {
      await logout();
      setMenuOpen(false);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  };

  const doSwitch = async () => {
    setBusy(true);
    setMenuError(null);
    try {
      await switchAccount();
      setMenuOpen(false);
    } catch (e) {
      setMenuError(e instanceof Error ? e.message : "No se pudo cambiar.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        className="menu-btn"
        onClick={() => setOpen((o) => !o)}
        aria-label="Abrir menú"
      >
        <Menu size={18} />
      </button>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      <aside className={`sidebar${open ? " open" : ""}`}>
        <div className="sidebar-brand">
          <h1>
            <Briefcase size={19} /> Job Agent
          </h1>
          <p>Gestión de ofertas laborales</p>
        </div>
        <nav className="sidebar-nav">
          {LINKS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `nav-link${isActive ? " active" : ""}`
              }
              onClick={() => setOpen(false)}
            >
              <Icon /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          {!configured && (
            <Link
              to="/login"
              className="sidebar-auth-note"
              title="Este despliegue no tiene las claves VITE_FIREBASE_* : el login está desactivado. Configúralas en Vercel y redeploya."
            >
              🔒 Sesión sin configurar
            </Link>
          )}
          {firebaseUser && (
            <div className="sidebar-user-block">
              {menuOpen && (
                <>
                  <div
                    className="user-menu-backdrop"
                    onClick={() => setMenuOpen(false)}
                  />
                  <div className="user-menu" role="menu">
                    <div className="user-menu-head">
                      <span className="user-menu-name">{displayName}</span>
                      {email && <span className="user-menu-mail">{email}</span>}
                    </div>
                    <button onClick={doSwitch} disabled={busy} role="menuitem">
                      <ArrowLeftRight size={14} />
                      {busy ? "Cambiando…" : "Cambiar de cuenta"}
                    </button>
                    <button onClick={doLogout} disabled={busy} role="menuitem">
                      <LogOut size={14} /> Cerrar sesión
                    </button>
                    {menuError && (
                      <p className="user-menu-error">{menuError}</p>
                    )}
                  </div>
                </>
              )}
              <button
                className="sidebar-user"
                onClick={() => setMenuOpen((o) => !o)}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                title={email || displayName}
              >
                {photo ? (
                  <img src={photo} alt="" className="avatar" referrerPolicy="no-referrer" />
                ) : (
                  <span className="avatar avatar-fallback">{initials}</span>
                )}
                <span className="sidebar-user-info">
                  <strong>{displayName}</strong>
                  {email && <small>{email}</small>}
                </span>
                <ChevronUp
                  size={14}
                  className={menuOpen ? "chev open" : "chev"}
                />
              </button>
            </div>
          )}
          API: {API_URL.replace(/^https?:\/\//, "")}
        </div>
      </aside>
    </>
  );
}
