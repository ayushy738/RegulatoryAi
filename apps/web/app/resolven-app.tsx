"use client";

import { useEffect } from "react";
import { AlertCircle, Loader2 } from "lucide-react";

import { AuthScreen } from "@/app/components/auth/AuthScreen";
import { LandingPage } from "@/app/components/auth/LandingPage";
import { AdminTopBar, TopBar } from "@/app/components/layout/TopBar";
import { EvidenceDrawer } from "@/app/components/ui/EvidenceDrawer";
import { RouteView } from "@/app/features/RouteView";
import { useWorkspace, WorkspaceProvider } from "@/app/workspace/WorkspaceContext";
import type { RouteKey } from "@/app/workspace/types";

export function ResolvenApp({
  initialRoute,
  initialEventId,
}: {
  initialRoute: RouteKey;
  initialEventId?: number;
}) {
  return (
    <WorkspaceProvider initialRoute={initialRoute} initialEventId={initialEventId}>
      <ResolvenShell />
    </WorkspaceProvider>
  );
}

function ResolvenShell() {
  const {
    route,
    canRead,
    authReady,
    loading,
    statusMessage,
    email,
    password,
    authMessage,
    setEmail,
    setPassword,
    setStatusMessage,
    handleSignIn,
  } = useWorkspace();
  const isAdminRoute = route.startsWith("admin");

  useEffect(() => {
    if (!statusMessage) return undefined;
    const timer = window.setTimeout(() => setStatusMessage(""), 2400);
    return () => window.clearTimeout(timer);
  }, [setStatusMessage, statusMessage]);

  if (route === "landing") {
    return (
      <LandingPage
        canRead={canRead}
        email={email}
        password={password}
        authMessage={authMessage}
        onEmail={setEmail}
        onPassword={setPassword}
        onSignIn={handleSignIn}
      />
    );
  }

  if (!authReady || loading) {
    return (
      <div className="center-screen">
        <Loader2 className="spin" size={28} />
        <p>Loading Resolven Regulatory AI...</p>
      </div>
    );
  }

  if (!canRead) {
    return (
      <AuthScreen
        email={email}
        password={password}
        message={authMessage}
        onEmail={setEmail}
        onPassword={setPassword}
        onSignIn={handleSignIn}
      />
    );
  }

  return (
    <div className={isAdminRoute ? "admin-shell" : "product-shell"}>
      {isAdminRoute ? <AdminTopBar /> : <TopBar />}
      <main className={isAdminRoute ? "admin-main-shell" : "product-main-shell"}>
        {statusMessage ? (
          <div className="status-banner">
            <AlertCircle size={18} />
            <span>{statusMessage}</span>
            <button type="button" onClick={() => setStatusMessage("")}>
              Dismiss
            </button>
          </div>
        ) : null}
        <RouteView />
      </main>
      <EvidenceDrawer />
    </div>
  );
}
