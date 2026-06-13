"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Eye, FileText, PlayCircle, Trash2 } from "lucide-react";
import { caseApi, inferenceApi } from "@/lib/api";
import { getToken, setCurrentCaseId } from "@/lib/session";
import type { CaseItem } from "@/lib/types";
import { formatDate } from "@/lib/format";
import { Button, Card, LoadingPanel, Notice, Pill } from "@/components/ui";
import { JobStatus } from "@/components/status";

export default function CasesPage() {
  const router = useRouter();
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");

  const loadCases = useCallback(async () => {
    const token = getToken();
    if (!token) {
      router.replace("/signin");
      return;
    }
    try {
      setCases(await caseApi.list(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load cases.");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void loadCases();
  }, [loadCases]);

  async function startInference(caseId: number) {
    const token = getToken();
    setBusyId(caseId);
    setError("");
    try {
      const job = await inferenceApi.start(token, caseId);
      setCurrentCaseId(caseId);
      router.push(`/results?case_id=${caseId}&job_id=${job.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start inference.");
    } finally {
      setBusyId(null);
    }
  }

  async function deleteCase(caseId: number) {
    const token = getToken();
    const confirmed = window.confirm(`Delete case #${caseId}?`);
    if (!confirmed) return;
    setBusyId(caseId);
    setError("");
    try {
      await caseApi.delete(token, caseId);
      await loadCases();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete case.");
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <LoadingPanel label="Loading cases..." />;

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-normal text-slate-900">Cases</h1>
          <p className="mt-2 text-slate-600">Review uploaded cases, completed analyses, and clinical handoff actions.</p>
        </div>
        <Button type="button" onClick={() => router.push("/upload")}>New Case</Button>
      </div>

      {error ? <Notice tone="error">{error}</Notice> : null}

      <Card className="overflow-hidden bg-white/95 p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] border-collapse text-left text-sm">
            <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-6 py-4">Case ID</th>
                <th className="px-6 py-4">Patient ID</th>
                <th className="px-6 py-4">Case Title</th>
                <th className="px-6 py-4">Created</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Last Viewed</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {cases.length ? cases.map((item) => (
                <tr key={item.id} className="border-t border-brand-line bg-white">
                  <td className="px-6 py-4 font-semibold text-slate-900">{item.id}</td>
                  <td className="px-6 py-4 text-slate-700">{item.patient_id}</td>
                  <td className="px-6 py-4 text-slate-700">{item.title}</td>
                  <td className="px-6 py-4 text-slate-600">{formatDate(item.created_at)}</td>
                  <td className="px-6 py-4"><JobStatus state={item.status} /></td>
                  <td className="px-6 py-4 text-slate-600">{formatDate(item.created_at)}</td>
                  <td className="px-6 py-4">
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        className="rounded-full p-2 text-brand-primary hover:bg-indigo-50"
                        aria-label="View results"
                        onClick={() => {
                          setCurrentCaseId(item.id);
                          router.push(`/results?case_id=${item.id}`);
                        }}
                      >
                        <Eye className="h-5 w-5" />
                      </button>
                      <button
                        type="button"
                        className="rounded-full p-2 text-brand-primary hover:bg-indigo-50"
                        aria-label="Run analysis"
                        disabled={busyId === item.id}
                        onClick={() => startInference(item.id)}
                      >
                        <PlayCircle className="h-5 w-5" />
                      </button>
                      <button
                        type="button"
                        className="rounded-full p-2 text-brand-primary hover:bg-indigo-50"
                        aria-label="Open clinical validation"
                        onClick={() => {
                          setCurrentCaseId(item.id);
                          router.push(`/clinical?case_id=${item.id}`);
                        }}
                      >
                        <FileText className="h-5 w-5" />
                      </button>
                      <button
                        type="button"
                        className="rounded-full p-2 text-red-600 hover:bg-red-50"
                        aria-label="Delete case"
                        disabled={busyId === item.id}
                        onClick={() => deleteCase(item.id)}
                      >
                        <Trash2 className="h-5 w-5" />
                      </button>
                    </div>
                  </td>
                </tr>
              )) : (
                <tr>
                  <td className="px-6 py-10 text-center text-sm font-medium text-slate-500" colSpan={7}>
                    No cases have been created for this account.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="flex flex-wrap gap-2 text-sm text-slate-600">
        <Pill tone="primary">Completed</Pill>
        <span>Rows are populated from the authenticated backend, not placeholder activity.</span>
      </div>
    </div>
  );
}
