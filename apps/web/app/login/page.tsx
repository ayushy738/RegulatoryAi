"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AuthScreen } from "@/app/components/auth/AuthScreen";
import { useAuth } from "@/app/components/auth/AuthProvider";

function safeDestination(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/login")) {
    return "/latest";
  }
  return value;
}

function LoginContent() {
  const { session, loading, login } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const destination = safeDestination(searchParams.get("next"));

  useEffect(() => {
    if (!loading && session) {
      router.replace(destination);
    }
  }, [destination, loading, router, session]);

  async function handleSignIn() {
    if (!email.trim() || !password) {
      setMessage("Enter your email address and password.");
      return;
    }

    setMessage("");
    setSubmitting(true);

    try {
      await login(email, password);
      router.replace(destination);
      router.refresh();
    } catch (error) {
      const detail = error instanceof Error ? error.message.toLowerCase() : "";
      setMessage(
        detail.includes("invalid login credentials")
          ? "The email or password is incorrect."
          : error instanceof Error
            ? error.message
            : "Unable to sign in. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthScreen
      email={email}
      password={password}
      message={message}
      loading={loading || submitting}
      onEmail={setEmail}
      onPassword={setPassword}
      onSignIn={handleSignIn}
    />
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="auth-route-loading" aria-live="polite">
          <p>Preparing secure sign in...</p>
        </main>
      }
    >
      <LoginContent />
    </Suspense>
  );
}
