"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { KeyRound, Mail, RefreshCcw, ShieldCheck } from "lucide-react";
import { API_BASE, authApi } from "@/lib/api";
import { setToken } from "@/lib/session";
import type { SSOProvider } from "@/lib/types";
import { Button, Card, Field, Notice, inputClass } from "@/components/ui";

const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export default function SignInPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [submittedEmail, setSubmittedEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [devOtp, setDevOtp] = useState("");
  const [providers, setProviders] = useState<SSOProvider[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);

  const primaryProvider = useMemo(
    () => providers.find((provider) => provider.provider === "microsoft") || providers[0],
    [providers],
  );
  const emailValid = emailPattern.test(email.trim());

  useEffect(() => {
    let mounted = true;
    authApi
      .ssoProviders()
      .then((items) => {
        if (mounted) setProviders(items);
      })
      .catch(() => {
        if (mounted) setProviders([]);
      });
    return () => {
      mounted = false;
    };
  }, []);

  async function sendOtp(targetEmail = email.trim()) {
    setError("");
    setNotice("");
    setSending(true);
    try {
      const response = await authApi.requestOtp(targetEmail);
      setSubmittedEmail(targetEmail);
      setNotice(response.message);
      if (response.dev_otp) {
        setDevOtp(response.dev_otp);
        setOtp(response.dev_otp);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send OTP. Please try again.");
    } finally {
      setSending(false);
    }
  }

  async function verifyOtp() {
    setError("");
    setVerifying(true);
    try {
      const token = await authApi.login(submittedEmail, otp.trim());
      setToken(token.access_token);
      const user = await authApi.me(token.access_token);
      router.replace(user.terms_accepted ? "/upload" : "/terms");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid OTP. Please try again.");
    } finally {
      setVerifying(false);
    }
  }

  function startSso(provider: SSOProvider) {
    if (!provider.enabled) return;
    window.location.assign(`${API_BASE}/api/v1/auth/sso/${provider.provider}/login`);
  }

  return (
    <main className="animated-bg grid min-h-screen place-items-center px-4 py-10">
      <Card className="w-full max-w-lg p-8">
        <div className="mb-8 text-center">
          <h1 className="mb-2 text-3xl font-bold text-slate-900">Sign In</h1>
          <p className="text-sm text-slate-600">Access your clinical diagnostic assistant</p>
        </div>

        {!submittedEmail ? (
          <div className="grid gap-4">
            <Field label="Email Address" hint={email && !emailValid ? "Please enter a valid email address" : undefined}>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-4 top-4 h-5 w-5 text-slate-400" />
                <input
                  className={`${inputClass} pl-12`}
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="clinician@example.com"
                />
              </div>
            </Field>

            {error ? <Notice tone="error">{error}</Notice> : null}

            <Button type="button" className="w-full" onClick={() => sendOtp()} disabled={sending || !emailValid}>
              {sending ? "Sending..." : "Send OTP Code"}
            </Button>

            <div className="my-2 flex items-center gap-3">
              <div className="h-px flex-1 bg-brand-line" />
              <span className="text-xs font-semibold text-slate-500">OR</span>
              <div className="h-px flex-1 bg-brand-line" />
            </div>

            {primaryProvider ? (
              <Button
                type="button"
                variant="secondary"
                disabled={!primaryProvider.enabled}
                onClick={() => startSso(primaryProvider)}
                title={primaryProvider.reason || undefined}
                className="w-full"
              >
                <ShieldCheck className="h-4 w-4" />
                Sign in with {primaryProvider.provider === "microsoft" ? "SSO" : titleCase(primaryProvider.provider)}
              </Button>
            ) : (
              <Button type="button" variant="secondary" className="w-full" disabled>
                Sign in with SSO
              </Button>
            )}
            {primaryProvider && !primaryProvider.enabled ? <Notice tone="warn">{primaryProvider.reason}</Notice> : null}
          </div>
        ) : (
          <div className="grid gap-4">
            <Notice tone="success">OTP code sent to {submittedEmail}</Notice>
            <Field label="Enter OTP Code">
              <div className="relative">
                <KeyRound className="pointer-events-none absolute left-4 top-4 h-5 w-5 text-slate-400" />
                <input
                  className={`${inputClass} pl-12`}
                  inputMode="numeric"
                  maxLength={6}
                  autoComplete="one-time-code"
                  value={otp}
                  onChange={(event) => setOtp(event.target.value)}
                  placeholder="123456"
                />
              </div>
            </Field>
            {devOtp ? (
              <Notice tone="info">
                Local development code: <span data-testid="dev-otp-code">{devOtp}</span>
              </Notice>
            ) : null}
            {notice ? <Notice tone="success">{notice}</Notice> : null}
            {error ? <Notice tone="error">{error}</Notice> : null}
            <div className="flex justify-end">
              <Button type="button" variant="ghost" onClick={() => sendOtp(submittedEmail)} disabled={sending}>
                <RefreshCcw className="h-4 w-4" />
                {sending ? "Sending..." : "Resend OTP"}
              </Button>
            </div>
            <Button type="button" className="w-full" onClick={verifyOtp} disabled={verifying || otp.trim().length < 4}>
              {verifying ? "Signing in..." : "Sign In"}
            </Button>
            <button
              type="button"
              onClick={() => {
                setSubmittedEmail("");
                setOtp("");
                setError("");
                setNotice("");
              }}
              className="text-sm font-medium text-brand-primary hover:underline"
            >
              Use a different email
            </button>
          </div>
        )}
      </Card>
    </main>
  );
}
