import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";

export function Layout() {
  return (
    <div className="layout">
      <Sidebar />
      <div className="main">
        <Outlet />
      </div>
    </div>
  );
}
