import { NavLink } from "react-router-dom";
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
    </nav>
  );
}

export default NavBar;
