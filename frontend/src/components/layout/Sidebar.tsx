import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  BarChart3,
  BookmarkX,
  Briefcase,
  Eye,
  FileText,
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
  { to: "/search", label: "Búsqueda", icon: Radar },
  { to: "/discarded", label: "Descartadas", icon: BookmarkX },
  { to: "/viewed", label: "Vistas", icon: Eye },
  { to: "/applications", label: "Postulaciones", icon: Send },
  { to: "/cv", label: "CV", icon: FileText },
  { to: "/analytics", label: "Análisis", icon: BarChart3 },
  { to: "/profile", label: "Perfil", icon: User },
  { to: "/settings", label: "Configuración", icon: Settings },
];

export function Sidebar() {
  const [open, setOpen] = useState(false);
  const { firebaseUser, profile, logout } = useAuth();

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
          {firebaseUser && (
            <div className="sidebar-user">
              <span title={profile?.email || firebaseUser.email || ""}>
                {profile?.nombre || firebaseUser.displayName || "Usuario"}
              </span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => void logout()}
                title="Cerrar sesion"
              >
                <LogOut size={13} /> Salir
              </button>
            </div>
          )}
          API: {API_URL.replace(/^https?:\/\//, "")}
        </div>
      </aside>
    </>
  );
}
