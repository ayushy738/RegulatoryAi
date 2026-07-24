"use client";

import { Loader2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";

import { useAuth } from "./AuthProvider";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (loading || session) return;
    const returnTo =
      pathname && pathname !== "/login" ? `?next=${encodeURIComponent(pathname)}` : "";
    router.replace(`/login${returnTo}`);
  }, [loading, pathname, router, session]);

  if (loading || !session) {
    return (
      <main className="auth-route-loading" aria-live="polite" aria-busy="true">
        <img src="/logo_mark.png" alt="" />
        <Loader2 className="spin" size={24} />
        <p>{loading ? "Restoring your secure session..." : "Redirecting to sign in..."}</p>
      </main>
    );
  }

  return children;
}
