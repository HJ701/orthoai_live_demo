"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import { inferenceApi } from "@/lib/api";
import { getToken } from "@/lib/session";
import type { InferenceStatus } from "@/lib/types";
import { Card, Notice, cn } from "@/components/ui";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function pct(status: InferenceStatus | null): number {
  if (!status) return 10;
  if (status.state === "done") return 100;
  if (status.state === "error") return 100;
  return Math.max(10, Math.min(99, Math.round(status.progress * 100)));
}

function stageIndex(status: InferenceStatus | null): number {
  if (!status) return 0;
  if (status.state === "queued") return 0;
  if (status.state === "running") return status.progress < 0.75 ? 1 : 2;
  return 2;
}

export default function InferencePage() {
  const router = useRouter();
  const params = useSearchParams();
  const caseId = useMemo(() => Number(params.get("case_id")), [params]);
  const jobId = useMemo(() => Number(params.get("job_id")), [params]);
  const [status, setStatus] = useState<InferenceStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      const token = getToken();
      if (!token) {
        router.replace("/signin");
        return;
      }
      if (!Number.isFinite(caseId) || !Number.isFinite(jobId) || caseId <= 0 || jobId <= 0) {
        setError("No inference job was selected.");
        return;
      }

      for (let attempt = 0; attempt < 120; attempt += 1) {
        try {
          const nextStatus = await inferenceApi.status(token, jobId, caseId);
          if (cancelled) return;
          setStatus(nextStatus);
          if (nextStatus.state === "done") {
            await sleep(900);
            if (!cancelled) router.replace(`/results?case_id=${caseId}&job_id=${jobId}`);
            return;
          }
          if (nextStatus.state === "error") {
            setError(nextStatus.error_message || "Inference could not be completed.");
            return;
          }
        } catch (err) {
          if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load inference status.");
          return;
        }
        await sleep(1000);
      }
      if (!cancelled) setError("Inference did not complete within the expected timeout.");
    }
    void poll();
    return () => {
      cancelled = true;
    };
  }, [caseId, jobId, router]);

  const percent = pct(status);
  const activeStage = stageIndex(status);
  const stages = ["Queued", "Processing", "Generating"];
  const heading = status?.state === "done" ? "Analysis complete. Opening results..." : "Your case has been queued for processing";

  return (
    <div className="grid min-h-[calc(100vh-220px)] place-items-center">
      <Card className="w-full max-w-5xl bg-white/95 px-10 py-16 text-center">
        <p className="mb-7 text-base text-slate-500">Case ID: {Number.isFinite(caseId) ? caseId : "-"}</p>
        <div className="mx-auto mb-12 grid max-w-lg grid-cols-3 gap-6">
          {stages.map((stage, index) => (
            <div key={stage} className="grid place-items-center gap-3">
              <div
                className={cn(
                  "grid h-16 w-16 place-items-center rounded-full text-xl font-semibold transition",
                  index <= activeStage ? "gradient-purple text-white shadow-panel" : "bg-slate-100 text-white",
                )}
              >
                {index + 1}
              </div>
              <p className={cn("text-sm", index <= activeStage ? "text-slate-600" : "text-slate-300")}>{stage}</p>
            </div>
          ))}
        </div>

        <div className="relative mx-auto mb-8 grid h-80 w-80 place-items-center">
          <div className="absolute h-52 w-52 animate-pulse rounded-full bg-gradient-to-br from-[#667eea] to-[#764ba2] shadow-[0_0_90px_rgba(99,102,241,0.36)]" />
          <div className="absolute h-48 w-48 animate-spin rounded-full border-[10px] border-white border-l-transparent opacity-95" />
          <div className="relative z-10 text-6xl font-light text-white">{percent}%</div>
        </div>

        <div className="mx-auto mb-10 h-3 max-w-4xl overflow-hidden rounded-full bg-slate-100">
          <div className="gradient-purple h-full rounded-full transition-all duration-700" style={{ width: `${percent}%` }} />
        </div>

        <h1 className="text-4xl font-normal text-slate-900">{heading}</h1>

        {error ? (
          <div className="mx-auto mt-5 max-w-4xl">
            <Notice tone="error">
              <span className="inline-flex items-center gap-3">
                <AlertCircle className="h-5 w-5 shrink-0" />
                {error}
              </span>
            </Notice>
          </div>
        ) : status?.state === "done" ? (
          <div className="mx-auto mt-5 max-w-4xl">
            <Notice tone="success">
              <span className="inline-flex items-center gap-3">
                <CheckCircle2 className="h-5 w-5 shrink-0" />
                Results are ready.
              </span>
            </Notice>
          </div>
        ) : null}

        <p className="mt-12 text-base text-slate-400">You can navigate away safely. Progress will continue in the background.</p>
      </Card>
    </div>
  );
}
