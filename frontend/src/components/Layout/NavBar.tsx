import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { ChangePasswordModal } from "../Auth/ChangePasswordModal";
import "./Layout.css";

// 4 top-level routes (2026-08 page-split redesign) -- NavLink's built-in
// active-state (isActive) covers current-page indication, no hand-rolled
// state needed.

const NAV_ITEMS = [
  { to: "/tasks", label: "Tasks" },
  { to: "/projects", label: "Projects" },
  { to: "/focus", label: "Focus" },
  { to: "/evaluation", label: "Evaluation" },
] as const;

export function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [changingPassword, setChangingPassword] = useState(false);

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <nav className="nav-bar">
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) => `nav-bar__link ${isActive ? "nav-bar__link--active" : ""}`}
        >
          {item.label}
        </NavLink>
      ))}
      {user && (
        <span className="nav-bar__account">
          <span className="nav-bar__username">{user.username}</span>
          <button
            type="button"
            className="nav-bar__logout"
            onClick={() => setChangingPassword(true)}
          >
            Change password
          </button>
          <button type="button" className="nav-bar__logout" onClick={handleLogout}>
            Log out
          </button>
        </span>
      )}
      {changingPassword && (
        <ChangePasswordModal onClose={() => setChangingPassword(false)} />
      )}
    </nav>
  );
}

export default NavBar;
