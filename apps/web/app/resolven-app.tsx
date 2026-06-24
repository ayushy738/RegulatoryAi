"use client";

import { AlertCircle, Loader2 } from "lucide-react";

import { AuthScreen } from "@/app/components/auth/AuthScreen";
import { LandingPage } from "@/app/components/auth/LandingPage";
import { Sidebar } from "@/app/components/layout/Sidebar";
import { TopBar } from "@/app/components/layout/TopBar";
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
    demoMode,
    isAdmin,
    userEmail,
    digestDate,
    pipelineStatus,
    events,
    statusMessage,
    email,
    password,
    authMessage,
    setEmail,
    setPassword,
    setStatusMessage,
    setDemoMode,
    handleSignIn,
    handleMagicLink,
    handleSignOut,
  } = useWorkspace();

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
        onMagicLink={handleMagicLink}
        onDemo={() => setDemoMode(true)}
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
        onMagicLink={handleMagicLink}
        onDemo={() => setDemoMode(true)}
      />
    );
  }

  return (
    <div className="app-shell">
      <Sidebar route={route} isAdmin={isAdmin || demoMode} userEmail={userEmail} onSignOut={handleSignOut} />
      <main className="main-shell">
        <TopBar
          route={route}
          digestDate={digestDate}
          pipelineStatus={pipelineStatus}
          eventCount={events.length}
          isAdmin={isAdmin || demoMode}
        />
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
    </div>
  );
}
