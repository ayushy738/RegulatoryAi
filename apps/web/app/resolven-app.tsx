"use client";

import { useEffect } from "react";
import { AlertCircle, Loader2, LockKeyhole } from "lucide-react";

import { LandingPage } from "@/app/components/auth/LandingPage";
import { ProtectedRoute } from "@/app/components/auth/ProtectedRoute";
import { AdminTopBar, TopBar } from "@/app/components/layout/TopBar";
import { Button } from "@/app/components/ui/Button";
import { EvidenceDrawer } from "@/app/components/ui/EvidenceDrawer";
import { TextField } from "@/app/components/ui/Field";
import { Overlay } from "@/app/components/ui/Overlay";
import { RouteView } from "@/app/features/RouteView";
import { useWorkspace, WorkspaceProvider } from "@/app/workspace/WorkspaceContext";
import type { RouteKey } from "@/app/workspace/types";

export function ResolvenApp({
  initialRoute,
  initialEventId,
  initialRunId,
}: {
  initialRoute: RouteKey;
  initialEventId?: number;
  initialRunId?: number;
}) {
  const workspace = (
    <WorkspaceProvider
      initialRoute={initialRoute}
      initialEventId={initialEventId}
      initialRunId={initialRunId}
    >
      <ResolvenShell />
    </WorkspaceProvider>
  );

  return initialRoute === "landing" ? workspace : <ProtectedRoute>{workspace}</ProtectedRoute>;
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
    authModalOpen,
    setEmail,
    setPassword,
    setStatusMessage,
    handleSignIn,
    closeAuthModal,
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

  return (
    <div className="rv-shell">
      {isAdminRoute ? <AdminTopBar /> : <TopBar />}
      <main className="rv-shell__main">
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
      <Overlay
        open={authModalOpen}
        onClose={closeAuthModal}
        title="Sign in to continue"
        description="Your session expired or this action needs an authenticated account."
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={closeAuthModal}>
              Cancel
            </Button>
            <Button variant="primary" Icon={LockKeyhole} onClick={() => void handleSignIn()}>
              Sign in
            </Button>
          </>
        }
      >
        <form
          className="rv-form"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSignIn();
          }}
        >
          {authMessage ? (
            <p className="rv-field__error" role="alert">
              {authMessage}
            </p>
          ) : null}
          <TextField
            label="Email"
            type="email"
            wide
            autoFocus
            autoComplete="email"
            value={email}
            placeholder="analyst@company.com"
            onChange={setEmail}
          />
          <TextField
            label="Password"
            type="password"
            wide
            autoComplete="current-password"
            value={password}
            placeholder="Enter password"
            onChange={setPassword}
          />
        </form>
      </Overlay>
    </div>
  );
}
