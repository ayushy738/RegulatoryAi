"use client";

import { useEffect } from "react";
import { AlertCircle, Loader2, LockKeyhole, X } from "lucide-react";

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
      {authModalOpen ? (
        <div className="auth-modal-backdrop" role="presentation" onClick={closeAuthModal}>
          <section
            className="auth-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="auth-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="auth-modal-header">
              <div>
                <LockKeyhole size={18} />
                <h2 id="auth-modal-title">Sign in to continue</h2>
              </div>
              <button type="button" aria-label="Close sign in" onClick={closeAuthModal}>
                <X size={18} />
              </button>
            </div>
            <form
              className="auth-modal-form"
              onSubmit={(event) => {
                event.preventDefault();
                void handleSignIn();
              }}
            >
              <label>
                Email
                <input
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="analyst@company.com"
                  type="email"
                  autoComplete="email"
                />
              </label>
              <label>
                Password
                <input
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Enter password"
                  type="password"
                  autoComplete="current-password"
                />
              </label>
              {authMessage ? <p className="notice">{authMessage}</p> : null}
              <div className="auth-modal-actions">
                <button type="button" className="secondary-button" onClick={closeAuthModal}>
                  Cancel
                </button>
                <button type="submit" className="primary-button">
                  Sign In
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </div>
  );
}
