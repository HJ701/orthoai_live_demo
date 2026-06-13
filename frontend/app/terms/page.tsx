"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CheckCircle2, ShieldCheck, X } from "lucide-react";
import { authApi } from "@/lib/api";
import { clearSession, getToken } from "@/lib/session";
import { Button, Card, LoadingPanel, Notice } from "@/components/ui";

const sections = [
  {
    title: "1. HIPAA/GDPR Compliance",
    body: "This application complies with HIPAA (Health Insurance Portability and Accountability Act) and GDPR (General Data Protection Regulation) requirements. All patient data is handled with strict confidentiality and security measures.",
  },
  {
    title: "2. Data Residency & UAE Disclaimer",
    body: "All data processed through this application is stored and processed within the UAE/GCC region. By using this service, you acknowledge that your data will remain within this geographic region in compliance with local data residency requirements.",
  },
  {
    title: "3. Patient Data Protection",
    body: "You are responsible for ensuring that all uploaded images are properly anonymized and do not contain Protected Health Information (PHI) such as patient names, faces, or other identifying information. The use of Patient ID/code is required instead of names.",
  },
  {
    title: "4. AI Diagnostic Tool Disclaimer",
    body: "This tool is for decision support only and is not a standalone diagnostic tool. All AI-generated findings must be reviewed and validated by qualified clinicians. The system provides assistance but does not replace professional clinical judgment.",
  },
  {
    title: "5. Consent & Authority",
    body: "By uploading clinical images, you confirm that you have obtained proper consent and have the authority to upload these images for analysis. You are responsible for maintaining appropriate documentation of patient consent.",
  },
];

export default function TermsPage() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    const token = getToken();
    if (!token) {
      router.replace("/signin");
      return;
    }
    authApi
      .me(token)
      .then((profile) => {
        if (!mounted) return;
        if (profile.terms_accepted) router.replace("/upload");
      })
      .catch(() => router.replace("/signin"))
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [router]);

  async function acceptTerms() {
    setSaving(true);
    setError("");
    try {
      await authApi.acceptTerms(getToken());
      router.replace("/upload");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to accept terms.");
      setSaving(false);
    }
  }

  function cancel() {
    clearSession();
    router.replace("/signin");
  }

  if (loading) return <LoadingPanel label="Loading terms..." />;

  return (
    <div className="mx-auto grid w-full max-w-3xl gap-5">
      <Card className="p-8">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full bg-indigo-50 text-brand-primary">
            <ShieldCheck className="h-7 w-7" />
          </div>
          <h1 className="text-3xl font-bold text-slate-900">Terms & Data Use Agreement</h1>
          <p className="mt-2 text-sm text-slate-600">Please review and accept the following terms to continue.</p>
        </div>

        <div className="grid gap-5 text-sm leading-6 text-slate-700">
          {sections.map((section) => (
            <section key={section.title}>
              <h2 className="mb-1 text-base font-semibold text-slate-900">{section.title}</h2>
              <p>{section.body}</p>
            </section>
          ))}
        </div>

        <label className="mt-6 flex cursor-pointer items-start gap-3 rounded-2xl border border-brand-line bg-white p-4 text-sm font-medium text-slate-700">
          <input
            className="mt-1 h-5 w-5 accent-brand-primary"
            type="checkbox"
            checked={checked}
            onChange={(event) => setChecked(event.target.checked)}
          />
          <span>
            I have read and agree to the Terms & Data Use Agreement, including HIPAA/GDPR compliance requirements and UAE data residency provisions.
          </span>
        </label>

        {error ? <div className="mt-5"><Notice tone="error">{error}</Notice></div> : null}

        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <Button type="button" variant="secondary" onClick={cancel}>
            <X className="h-4 w-4" />
            Cancel
          </Button>
          <Button type="button" onClick={acceptTerms} disabled={!checked || saving}>
            <CheckCircle2 className="h-4 w-4" />
            {saving ? "Accepting..." : "Accept & Continue"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
