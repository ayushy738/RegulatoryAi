import type { NormalizedRoute } from "@/app/workspace/types";

const workspaceNav: Array<{
  href: string;
  label: string;
  route: NormalizedRoute;
  icon: string;
  filled: boolean;
  adminOnly: boolean;
}> = [
  { href: "/dashboard", label: "Dashboard", route: "dashboard", icon: "dashboard", filled: false, adminOnly: false },
  { href: "/latest", label: "Latest", route: "latest", icon: "newspaper", filled: false, adminOnly: false },
  { href: "/intelligence", label: "Intelligence", route: "intelligence", icon: "analytics", filled: false, adminOnly: false },
  { href: "/deadlines", label: "Deadlines", route: "deadlines", icon: "event", filled: false, adminOnly: false },
  { href: "/ask", label: "Ask AI", route: "ask", icon: "auto_awesome", filled: true, adminOnly: false },
  { href: "/admin/sources", label: "Sources", route: "admin-sources", icon: "menu_book", filled: false, adminOnly: true },
  { href: "/notifications", label: "Digests", route: "notifications", icon: "mail", filled: false, adminOnly: false },
];

function MaterialIcon({ children, filled = false }: { children: string; filled?: boolean }) {
  return (
    <span className="material-symbols-outlined" style={filled ? { fontVariationSettings: "'FILL' 1" } : undefined}>
      {children}
    </span>
  );
}

export function Sidebar({
  route,
  isAdmin,
  userEmail,
  onSignOut: _onSignOut,
}: {
  route: NormalizedRoute;
  isAdmin: boolean;
  userEmail: string;
  onSignOut: () => void;
}) {
  return (
    <aside className="sidebar">
      <a className="brand-block stitch-brand-block" href="/dashboard">
        <strong>RegIntell</strong>
        <span>Regulatory Intelligence</span>
      </a>
      <nav>
        {workspaceNav
          .filter((item) => !item.adminOnly || isAdmin)
          .map((item) => (
            <a key={item.href} className={route === item.route ? "active" : ""} href={item.href}>
              <MaterialIcon filled={item.filled}>{item.icon}</MaterialIcon>
              {item.label}
            </a>
          ))}
      </nav>
      <div className="stitch-sidebar-footer">
        <a className={route === "account" ? "active" : ""} href="/account">
          <MaterialIcon>person</MaterialIcon>
          Profile
        </a>
        {isAdmin ? (
          <a className={route === "admin-dashboard" ? "active" : ""} href="/admin">
            <MaterialIcon>admin_panel_settings</MaterialIcon>
            Admin
          </a>
        ) : null}
        <span>{userEmail}</span>
      </div>
    </aside>
  );
}
