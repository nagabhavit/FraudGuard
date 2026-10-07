import {
  Activity,
  BarChart3,
  ChevronsLeft,
  ChevronsRight,
  LayoutDashboard,
  Receipt,
  ShieldAlert,
  ShieldHalf,
} from "lucide-react";
import { NavLink } from "react-router-dom";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/transactions", label: "Transactions", icon: Receipt },
  { to: "/investigations", label: "Investigations", icon: ShieldAlert },
  { to: "/models", label: "Models", icon: ShieldHalf },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/health", label: "System Health", icon: Activity },
];

export function Sidebar({
  collapsed,
  onToggleCollapsed,
}: {
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-mark">
          <ShieldHalf size={18} />
        </div>
        <span className="sidebar-brand-text">FraudGuard</span>
      </div>

      <nav className="sidebar-nav" aria-label="Primary">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `sidebar-nav-item${isActive ? " active" : ""}`
            }
            title={collapsed ? label : undefined}
          >
            <Icon size={18} />
            <span className="sidebar-nav-item-label">{label}</span>
          </NavLink>
        ))}
      </nav>

      <button
        type="button"
        className="sidebar-collapse-toggle"
        onClick={onToggleCollapsed}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
        <span className="sidebar-collapse-toggle-label">Collapse</span>
      </button>
    </aside>
  );
}
