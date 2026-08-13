import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import { CamerasPage } from "./pages/CamerasPage";
import { ChannelsPage } from "./pages/ChannelsPage";
import { EventsPage } from "./pages/EventsPage";
import { LoginPage } from "./pages/LoginPage";

export function App() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="page-loading">Conectando con el sistema…</div>;
  }

  if (!user) {
    if (location.pathname !== "/login") return <Navigate to="/login" replace />;
    return <LoginPage />;
  }

  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<CamerasPage />} />
        <Route path="/eventos" element={<EventsPage />} />
        <Route path="/canales" element={<ChannelsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

function Shell() {
  const { user, logout } = useAuth();
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">
          secuh<span className="brand-dot" aria-hidden="true">
            ·
          </span>
        </span>
        <nav className="nav" aria-label="Secciones">
          <NavLink to="/" end>
            Cámaras
          </NavLink>
          <NavLink to="/eventos">Eventos</NavLink>
          <NavLink to="/canales">Canales</NavLink>
        </nav>
        <div className="topbar-user">
          <span className="username">{user?.username}</span>
          <button className="btn btn-ghost" onClick={() => void logout()}>
            Cerrar sesión
          </button>
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
