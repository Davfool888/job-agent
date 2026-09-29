import { Link } from "react-router-dom";
import { Header } from "../components/layout/Header";

export function NotFound() {
  return (
    <>
      <Header title="No encontrada" />
      <div className="content">
        <div className="state-box">
          <h3>Página no existe (404).</h3>
          <p>
            <Link to="/dashboard">Volver al Dashboard</Link>
          </p>
        </div>
      </div>
    </>
  );
}
