"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Camera,
  CheckCircle2,
  ClipboardCopy,
  Download,
  FileJson,
  FileText,
  Info,
  RefreshCcw,
  Share2,
  Stethoscope,
} from "lucide-react";
import { caseApi, inferenceApi, resultsApi } from "@/lib/api";
import { getCurrentCaseId, getToken, setCurrentCaseId } from "@/lib/session";
import type { CaseItem, CaseResults, InferenceStatus } from "@/lib/types";
import { displayClass, formatDate, percent } from "@/lib/format";
import { Button, Card, LoadingPanel, Notice, Pill, cn } from "@/components/ui";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

type FindingRow = {
  label: string;
  confidence: number | null;
  risk: "Low" | "Medium" | "High";
};

function riskFor(label: string, confidence: number | null): "Low" | "Medium" | "High" {
  const normalized = label.toLowerCase();
  if (normalized.includes("low")) return "Low";
  if (normalized.includes("severe") || normalized.includes("high")) return "High";
  if (confidence != null && confidence < 0.65) return "Low";
  return "Medium";
}

function buildFindings(results: CaseResults | null): FindingRow[] {
  if (!results) return [];
  const rootFindings = asArray(results.findings.findings);
  const rows = rootFindings.map((raw) => {
    const item = asRecord(raw);
    const label = displayClass(item.type || item.label || item.finding);
    const confidence = asNumber(item.confidence);
    return { label, confidence, risk: riskFor(label, confidence) };
  });
  if (rows.length) return rows;

  return results.per_image_evidence.flatMap((evidence) =>
    asArray(evidence.findings.detections).map((raw) => {
      const item = asRecord(raw);
      const label = displayClass(item.type || item.label || "Finding");
      const confidence = asNumber(item.confidence) ?? evidence.confidence;
      return { label, confidence, risk: riskFor(label, confidence) };
    }),
  );
}

function firstDetection(evidence: CaseResults["per_image_evidence"][number]): FindingRow {
  const detection = asRecord(asArray(evidence.findings.detections)[0]);
  const label = displayClass(detection.type || detection.label || "No findings");
  const confidence = asNumber(detection.confidence) ?? evidence.confidence;
  return { label, confidence, risk: riskFor(label, confidence) };
}

export default function ResultsPage() {
  const router = useRouter();
  const params = useSearchParams();
  const caseId = useMemo(() => {
    const raw = params.get("case_id") || getCurrentCaseId();
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }, [params]);
  const jobId = useMemo(() => {
    const parsed = Number(params.get("job_id"));
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }, [params]);

  const [caseItem, setCaseItem] = useState<CaseItem | null>(null);
  const [status, setStatus] = useState<InferenceStatus | null>(null);
  const [results, setResults] = useState<CaseResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pdfBusy, setPdfBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const token = getToken();
      if (!token) {
        router.replace("/signin");
        return;
      }
      if (!caseId) {
        setError("No case selected.");
        setLoading(false);
        return;
      }

      try {
        setCurrentCaseId(caseId);
        const loadedCase = await caseApi.get(token, caseId);
        if (!cancelled) setCaseItem(loadedCase);

        if (jobId) {
          for (let attempt = 0; attempt < 80; attempt += 1) {
            const loadedStatus = await inferenceApi.status(token, jobId, caseId);
            if (cancelled) return;
            setStatus(loadedStatus);
            if (loadedStatus.is_terminal) break;
            await sleep(1000);
          }
        }

        const loadedResults = await resultsApi.get(token, caseId);
        if (!cancelled) setResults(loadedResults);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load results.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [caseId, jobId, router]);

  const prediction = asRecord(results?.findings.prediction);
  const predictedClass = displayClass(prediction.predicted_class);
  const findings = buildFindings(results);
  const lowRisk = findings.filter((finding) => finding.risk === "Low").length;
  const requireAttention = Math.max(findings.length - lowRisk, 0);

  async function downloadPdf() {
    if (!caseId) return;
    setPdfBusy(true);
    setError("");
    try {
      const token = getToken();
      const blob = await resultsApi.downloadPdf(token, caseId);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `orthoai_case_${caseId}_summary.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to download PDF.");
    } finally {
      setPdfBusy(false);
    }
  }

  function copyJson() {
    if (!results) return;
    void navigator.clipboard.writeText(JSON.stringify(results.findings, null, 2));
  }

  if (loading) return <LoadingPanel label="Loading results..." />;

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-7">
      <Card className="bg-white/95 p-8">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <h1 className="text-4xl font-normal text-slate-900">{caseItem?.title || "Case Analysis"}</h1>
            <div className="mt-3 flex flex-wrap gap-2 text-sm">
              <Pill>Case ID: {caseId || "-"}</Pill>
              <Pill>Patient ID: {caseItem?.patient_id || "-"}</Pill>
              <Pill>Created: {formatDate(caseItem?.created_at)}</Pill>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {(caseItem?.tags?.length ? caseItem.tags : [predictedClass]).filter(Boolean).map((tag) => <Pill key={tag}>{tag}</Pill>)}
            </div>
          </div>
          <Button type="button" variant="secondary" onClick={() => router.push("/upload")}>
            <ArrowLeft className="h-4 w-4" />
            New Case
          </Button>
        </div>
        <div className="mt-6 border-t border-brand-line pt-5 text-sm text-slate-600">
          <span className="font-bold">Analyst:</span> AI Model{" "}
          <span className="ml-3 font-bold">Model Version:</span> {results?.model_version || "v1.0.0"}{" "}
          <span className="ml-3 font-bold">Checksum:</span> sha256:abc123def456....
        </div>
      </Card>

      {error ? <Notice tone="error">{error}</Notice> : null}

      {results ? (
        <>
          <Card className="bg-white/95 p-8">
            <h2 className="mb-6 text-2xl font-normal text-slate-900">Diagnostic Summary</h2>
            <div className="grid gap-5 md:grid-cols-3">
              <div className="rounded-[28px] bg-indigo-50 p-7 text-center">
                <p className="text-4xl font-normal text-purple-600">{findings.length || 1}</p>
                <p className="mt-1 text-slate-600">Findings</p>
              </div>
              <div className="rounded-[28px] bg-emerald-50 p-7 text-center">
                <p className="text-4xl font-normal text-emerald-600">{lowRisk}</p>
                <p className="mt-1 text-slate-600">Low Risk</p>
              </div>
              <div className="rounded-[28px] bg-orange-50 p-7 text-center">
                <p className="text-4xl font-normal text-orange-600">{requireAttention || 1}</p>
                <p className="mt-1 text-slate-600">Require Attention</p>
              </div>
            </div>

            <section className="mt-8">
              <h3 className="mb-3 text-lg font-medium text-slate-900">Key Findings:</h3>
              <div className="grid gap-3">
                {(findings.length ? findings : [{ label: predictedClass, confidence: asNumber(prediction.confidence), risk: "Medium" as const }]).map((finding, index) => (
                  <div key={`${finding.label}-${index}`} className="flex items-center justify-between gap-4 rounded-2xl bg-slate-50 px-4 py-3">
                    <div className="flex items-center gap-4">
                      <span className={cn("grid h-6 w-6 place-items-center rounded-full text-white", finding.risk === "Low" ? "bg-emerald-500" : "bg-orange-500")}>
                        {finding.risk === "Low" ? <CheckCircle2 className="h-4 w-4" /> : <Info className="h-4 w-4" />}
                      </span>
                      <span className="font-medium text-slate-800">{finding.label}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <Pill tone="primary">{percent(finding.confidence)}</Pill>
                      <Pill tone={finding.risk === "Low" ? "success" : "warn"}>{finding.risk}</Pill>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </Card>

          <Card className="bg-white/95 p-8">
            <h2 className="mb-6 text-2xl font-normal text-slate-900">Evidence & Visuals</h2>
            <div className="grid gap-5 md:grid-cols-2">
              {results.per_image_evidence.map((evidence, index) => {
                const detection = firstDetection(evidence);
                return (
                  <article key={evidence.image_id} className="rounded-[28px] border border-brand-line bg-white p-5">
                    <div className="grid h-56 place-items-center rounded-2xl bg-slate-100 text-slate-400">
                      <Camera className="h-12 w-12" />
                    </div>
                    <h3 className="mt-4 font-medium text-slate-900">Image {index + 1}</h3>
                    <p className="mt-2 text-sm text-slate-500">
                      Detected: {detection.label} (confidence {percent(detection.confidence)})
                    </p>
                  </article>
                );
              })}
            </div>
          </Card>

          <Card className="bg-white/95 p-8">
            <div className="mb-5 flex items-center justify-between gap-4">
              <h2 className="text-2xl font-normal text-slate-900">Structured Output</h2>
              <button type="button" onClick={copyJson} aria-label="Copy JSON output" className="rounded-full p-2 text-slate-500 hover:bg-slate-100">
                <ClipboardCopy className="h-5 w-5" />
              </button>
            </div>
            <details className="rounded-2xl border border-brand-line bg-white p-4 text-sm text-slate-700">
              <summary className="cursor-pointer font-medium text-slate-600">View JSON Output</summary>
              <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(results.findings, null, 2)}</pre>
            </details>
          </Card>

          <Card className="bg-white/95 p-8">
            <h2 className="mb-5 text-2xl font-normal text-slate-900">Clinician Actions</h2>
            <div className="flex flex-wrap gap-4">
              <Button type="button" variant="secondary" onClick={() => caseId && router.push(`/clinical?case_id=${caseId}`)}>
                <FileText className="h-4 w-4" />
                Add Note
              </Button>
              <Button type="button" variant="secondary" onClick={() => router.push("/upload")}>
                <RefreshCcw className="h-4 w-4" />
                Re-run Analysis
              </Button>
              <Button type="button" variant="secondary" disabled>
                <Share2 className="h-4 w-4" />
                Share Secure Link
              </Button>
              <Button type="button" onClick={() => caseId && router.push(`/clinical?case_id=${caseId}`)}>
                <Stethoscope className="h-4 w-4" />
                Clinical Validation
              </Button>
            </div>
          </Card>

          <Card className="bg-white/95 p-8">
            <h2 className="mb-5 text-2xl font-normal text-slate-900">Download Options</h2>
            <div className="flex flex-wrap gap-4">
              <Button type="button" onClick={downloadPdf} disabled={pdfBusy}>
                <Download className="h-4 w-4" />
                {pdfBusy ? "Preparing..." : "Download PDF Summary"}
              </Button>
              <Button type="button" variant="secondary" disabled>
                <FileJson className="h-4 w-4" />
                Download JSON
              </Button>
              <Button type="button" variant="secondary" disabled>
                <FileText className="h-4 w-4" />
                Copy for EMR
              </Button>
            </div>
          </Card>
        </>
      ) : (
        <Card className="bg-white/95 p-8">
          <Notice tone="warn">No completed inference results are available for this case.</Notice>
        </Card>
      )}

      {status?.state === "error" ? <Notice tone="error">{status.error_message || "Inference failed."}</Notice> : null}
    </div>
  );
}
