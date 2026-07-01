import Link from "next/link";
import { LogOut } from "lucide-react";

import { adminNav, userNav } from "@/app/workspace/nav";
import type { NavItem, NormalizedRoute } from "@/app/workspace/types";

function NavLink({ item, route }: { item: NavItem; route: NormalizedRoute }) {
  const active = route === item.route;
  return (
    <Link className={active ? "active" : ""} href={item.href} aria-current={active ? "page" : undefined}>
      <item.Icon size={17} />
      <span>{item.label}</span>
    </Link>
  );
}

export function Sidebar({
  route,
  isAdmin,
  userEmail,
  onSignOut,
}: {
  route: NormalizedRoute;
  isAdmin: boolean;
  userEmail: string;
  onSignOut: () => void;
}) {
  const mobileNav = [userNav[0], userNav[1], userNav[2], userNav[3], userNav[4]];
  return (
    <>
      <aside className="sidebar ops-sidebar">
        <Link className="brand-block ops-brand" href="/dashboard">
          <strong>RegIntell</strong>
          <span>Regulatory Intelligence</span>
        </Link>

        <nav aria-label="Workspace navigation">
          <span className="nav-label">Workspace</span>
          {userNav.map((item) => (
            <NavLink key={item.href} item={item} route={route} />
          ))}
          {isAdmin ? (
            <>
              <span className="nav-label">Operations</span>
              {adminNav.map((item) => (
                <NavLink key={item.href} item={item} route={route} />
              ))}
            </>
          ) : null}
        </nav>

        <div className="stitch-sidebar-footer ops-sidebar-footer">
          <span title={userEmail}>{userEmail || "Not signed in"}</span>
          <button className="sign-out" type="button" onClick={onSignOut}>
            <LogOut size={17} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        {mobileNav.map((item) => (
          <Link key={item.href} className={route === item.route ? "active" : ""} href={item.href}>
            <item.Icon size={18} />
            <span>{item.label}</span>
          </Link>
        ))}
      </nav>
    </>
  );
}
