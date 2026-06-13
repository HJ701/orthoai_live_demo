"use client";

import { useEffect, useState } from "react";
import { ClipboardList, LockKeyhole, ShieldCheck, UserCircle } from "lucide-react";
import { userApi } from "@/lib/api";
import { getToken } from "@/lib/session";
import type { Activity } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { Card, LoadingPanel, Notice, Pill } from "@/components/ui";
import { JobStatus } from "@/components/status";

function detailsText(details: Record<string, unknown>): string {
  const keys = Object.keys(details);
  if (keys.length === 0) return "-";
  return JSON.stringify(details);
}

export default function AccountPage() {
  const [activity, setActivity] = useState<Activity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    const token = getToken();
    userApi
      .activity(token)
      .then((loaded) => {
        if (mounted) setActivity(loaded);
      })
      .catch((err) => {
        if (mounted) setError(err instanceof Error ? err.message : "Unable to load account activity.");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) return <LoadingPanel label="Loading account..." />;

  return (
    <div className="grid gap-5">
      {error ? <Notice tone="error">{error}</Notice> : null}

      <Card className="bg-white/95 p-8">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="flex items-start gap-3">
            <div className="rounded-full bg-indigo-50 p-3 text-brand-primary">
              <UserCircle className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-3xl font-normal text-brand-ink">Account & Audit Log</h1>
              <p className="mt-1 text-sm leading-6 text-brand-muted">Account Information</p>
            </div>
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-4">
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-brand-muted">Email</p>
            <p className="mt-2 break-all text-sm font-bold text-brand-ink">{activity?.user.email || "-"}</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-brand-muted">Role</p>
            <p className="mt-2 text-sm font-bold capitalize text-brand-ink">{activity?.user.auth_provider === "email" ? "Clinician" : activity?.user.auth_provider || "-"}</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-brand-muted">Data Residency</p>
            <p className="mt-2 text-sm font-bold text-brand-ink">UAE/GCC</p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-xs font-bold uppercase tracking-wide text-brand-muted">Terms & Conditions</p>
            <p className="mt-2 text-sm font-bold text-brand-ink">{activity?.user.terms_accepted ? "Accepted" : "Pending"}</p>
          </div>
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="bg-white/95 p-6">
          <div className="mb-4 flex items-center gap-3">
            <ClipboardList className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-bold text-brand-ink">Cases</h2>
          </div>
          <div className="grid gap-3">
            {activity?.cases.length ? activity.cases.map((item) => (
              <div key={item.id} className="rounded-2xl border border-brand-line bg-white p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-bold text-brand-ink">{item.title || `Case #${item.id}`}</p>
                  <JobStatus state={item.status} />
                </div>
                <p className="mt-1 text-sm font-semibold text-brand-muted">{item.patient_id || "-"} · {formatDate(item.created_at)}</p>
              </div>
            )) : <p className="text-sm font-semibold text-brand-muted">No case activity recorded.</p>}
          </div>
        </Card>

        <Card className="bg-white/95 p-6">
          <div className="mb-4 flex items-center gap-3">
            <ShieldCheck className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-bold text-brand-ink">Clinical Validations</h2>
          </div>
          <div className="grid gap-3">
            {activity?.clinical_validations.length ? activity.clinical_validations.map((item) => (
              <div key={item.id} className="rounded-2xl border border-brand-line bg-white p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-bold text-brand-ink">{item.case_id}</p>
                  <Pill tone={item.class_match ? "success" : "warn"}>{item.class_match ? "match" : "review"}</Pill>
                </div>
                <p className="mt-1 text-sm font-semibold text-brand-muted">{item.site} · OrthoAI case #{item.orthoai_case_id} · {formatDate(item.created_at)}</p>
              </div>
            )) : <p className="text-sm font-semibold text-brand-muted">No clinical validation activity recorded.</p>}
          </div>
        </Card>
      </div>

      <Card className="bg-white/95 p-6">
        <div className="mb-4 flex items-center gap-3">
          <LockKeyhole className="h-5 w-5 text-brand-primary" />
          <h2 className="text-lg font-bold text-brand-ink">Audit Log</h2>
          <span className="text-sm font-medium text-slate-500">Security</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-brand-line text-xs uppercase tracking-wide text-brand-muted">
                <th className="py-3 pr-4">Time</th>
                <th className="py-3 pr-4">Action</th>
                <th className="py-3 pr-4">Resource</th>
                <th className="py-3 pr-4">Details</th>
              </tr>
            </thead>
            <tbody>
              {activity?.audit_logs.length ? activity.audit_logs.map((item) => (
                <tr key={item.id} className="border-b border-brand-line last:border-0">
                  <td className="py-3 pr-4 font-semibold text-brand-muted">{formatDate(item.created_at)}</td>
                  <td className="py-3 pr-4 font-bold text-brand-ink">{item.action}</td>
                  <td className="py-3 pr-4 text-slate-700">{item.resource_type} {item.resource_id ? `#${item.resource_id}` : ""}</td>
                  <td className="py-3 pr-4 text-slate-600">{detailsText(item.details)}</td>
                </tr>
              )) : (
                <tr>
                  <td className="py-3 pr-4 text-sm font-semibold text-brand-muted" colSpan={4}>No audit entries recorded.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
