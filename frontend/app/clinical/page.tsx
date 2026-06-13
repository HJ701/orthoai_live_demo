"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Save, Stethoscope, TableProperties } from "lucide-react";
import { caseApi, clinicalApi, resultsApi } from "@/lib/api";
import { getCurrentCaseId, getToken, setCurrentCaseId } from "@/lib/session";
import type { CaseItem, CaseResults, ClinicalList, ClinicalPayload, ClinicalStats } from "@/lib/types";
import { displayClass, formatDate, percent, seconds } from "@/lib/format";
import { Button, Card, Field, LoadingPanel, Notice, Pill, inputClass } from "@/components/ui";
import { JobStatus } from "@/components/status";

const classOptions = ["Class I", "Class II div 1", "Class II div 2", "Class III", "Unclassifiable"];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function normalizeClass(value: string): string {
  return classOptions.includes(value) ? value : "Unclassifiable";
}

export default function ClinicalPage() {
  const router = useRouter();
  const params = useSearchParams();
  const caseId = useMemo(() => {
    const raw = params.get("case_id") || getCurrentCaseId();
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }, [params]);

  const [cases, setCases] = useState<CaseItem[]>([]);
  const [caseItem, setCaseItem] = useState<CaseItem | null>(null);
  const [results, setResults] = useState<CaseResults | null>(null);
  const [clinicalList, setClinicalList] = useState<ClinicalList | null>(null);
  const [stats, setStats] = useState<ClinicalStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  const [site, setSite] = useState("DEMO");
  const [clinicalCaseId, setClinicalCaseId] = useState(() => `VAL-${Date.now()}`);
  const [clinician, setClinician] = useState("Demo clinician");
  const [manualClass, setManualClass] = useState("Class I");
  const [dhc, setDhc] = useState("4");
  const [ac, setAc] = useState("6");
  const [manualTime, setManualTime] = useState("4");
  const [useful, setUseful] = useState("4");
  const [agree, setAgree] = useState<"Agree" | "Partial" | "Disagree">("Agree");
  const [overrideValue, setOverrideValue] = useState<"No" | "Yes">("No");
  const [comment, setComment] = useState("");

  const prediction = asRecord(results?.findings.prediction);
  const timings = asRecord(results?.findings.timings);
  const aiClass = normalizeClass(displayClass(prediction.predicted_class));
  const aiConfidence = asNumber(prediction.confidence);
  const aiSeconds = asNumber(timings.total_inference_seconds);

  async function loadClinical(selectedCaseId: number) {
    const token = getToken();
    setError("");
    const [loadedCase, loadedResults, loadedList, loadedStats] = await Promise.all([
      caseApi.get(token, selectedCaseId),
      resultsApi.get(token, selectedCaseId),
      clinicalApi.list(token, selectedCaseId),
      clinicalApi.stats(token, selectedCaseId),
    ]);
    setCaseItem(loadedCase);
    setResults(loadedResults);
    setClinicalList(loadedList);
    setStats(loadedStats);
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const token = getToken();
      if (!token) {
        router.replace("/signin");
        return;
      }
      try {
        const loadedCases = await caseApi.list(token);
        if (cancelled) return;
        setCases(loadedCases);

        if (!caseId) {
          return;
        }

        setCurrentCaseId(caseId);
        await clinicalApi.health(token, caseId);
        if (!cancelled) await loadClinical(caseId);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load clinical validation.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [caseId, router]);

  async function saveValidation() {
    if (!caseId) return;
    const token = getToken();
    setSaving(true);
    setError("");
    setSaved("");
    try {
      const payload: ClinicalPayload = {
        site: site.trim(),
        case_id: clinicalCaseId.trim(),
        assess_date: today(),
        clinician: clinician.trim() || null,
        rec_opg: true,
        rec_photo: true,
        rec_other: false,
        m_class: manualClass,
        dhc: Number(dhc),
        ac: ac ? Number(ac) : null,
        t_manual: manualTime ? Number(manualTime) : null,
        ai_class: aiClass,
        ai_dhc: null,
        ai_ac: null,
        ai_conf: aiConfidence == null ? null : Math.round(aiConfidence * 1000) / 10,
        t_ai: aiSeconds == null ? null : Math.round((aiSeconds / 60) * 100) / 100,
        calib: "N/A",
        agree,
        override: overrideValue,
        override_reason: overrideValue === "Yes" ? comment.trim() || "Clinical override recorded." : null,
        useful: useful ? Number(useful) : null,
        comment: comment.trim() || null,
      };
      await clinicalApi.create(token, caseId, payload);
      setSaved("Clinical validation saved.");
      setClinicalCaseId(`VAL-${Date.now()}`);
      await loadClinical(caseId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save clinical validation.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingPanel label="Loading clinical validation..." />;

  if (!caseId) {
    return (
      <div className="grid gap-5">
        <Card>
          <h1 className="text-2xl font-bold text-brand-ink">Clinical Validation</h1>
          <p className="mt-1 text-sm leading-6 text-brand-muted">Select a completed case to open validation.</p>
        </Card>
        <div className="grid gap-3">
          {cases.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => router.push(`/clinical?case_id=${item.id}`)}
              className="flex items-center justify-between gap-4 rounded-app border border-brand-line bg-white p-4 text-left shadow-sm hover:border-brand-primary"
            >
              <span>
                <span className="block font-bold text-brand-ink">{item.title}</span>
                <span className="text-sm font-semibold text-brand-muted">#{item.id} · {item.patient_id}</span>
              </span>
              <JobStatus state={item.status} />
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
      <Card>
        <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="rounded-lg bg-teal-50 p-3 text-brand-primary">
              <Stethoscope className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-brand-ink">Clinical Validation</h1>
              <p className="mt-1 text-sm leading-6 text-brand-muted">
                {caseItem ? `${caseItem.title} · ${caseItem.patient_id}` : `Case #${caseId}`}
              </p>
            </div>
          </div>
          <Button type="button" variant="secondary" onClick={() => router.push(`/results?case_id=${caseId}`)}>
            Results
          </Button>
        </div>

        {error ? <Notice tone="error">{error}</Notice> : null}
        {saved ? <div className="mt-3"><Notice tone="success">{saved}</Notice></div> : null}

        <div className="mt-5 grid gap-5 md:grid-cols-2">
          <Field label="Site">
            <input aria-label="Site" className={inputClass} value={site} onChange={(event) => setSite(event.target.value)} />
          </Field>
          <Field label="Validation case ID">
            <input aria-label="Validation case ID" className={inputClass} value={clinicalCaseId} onChange={(event) => setClinicalCaseId(event.target.value)} />
          </Field>
          <Field label="Clinician">
            <input aria-label="Clinician" className={inputClass} value={clinician} onChange={(event) => setClinician(event.target.value)} />
          </Field>
          <Field label="Manual class">
            <select aria-label="Manual class" className={inputClass} value={manualClass} onChange={(event) => setManualClass(event.target.value)}>
              {classOptions.map((option) => <option key={option}>{option}</option>)}
            </select>
          </Field>
          <Field label="DHC">
            <input aria-label="DHC" className={inputClass} type="number" min="1" max="5" value={dhc} onChange={(event) => setDhc(event.target.value)} />
          </Field>
          <Field label="AC">
            <input aria-label="AC" className={inputClass} type="number" min="1" max="10" value={ac} onChange={(event) => setAc(event.target.value)} />
          </Field>
          <Field label="Manual time minutes">
            <input aria-label="Manual time minutes" className={inputClass} type="number" min="0" step="0.1" value={manualTime} onChange={(event) => setManualTime(event.target.value)} />
          </Field>
          <Field label="Useful score">
            <input aria-label="Useful score" className={inputClass} type="number" min="1" max="5" value={useful} onChange={(event) => setUseful(event.target.value)} />
          </Field>
          <Field label="Agreement">
            <select aria-label="Agreement" className={inputClass} value={agree} onChange={(event) => setAgree(event.target.value as "Agree" | "Partial" | "Disagree")}>
              <option>Agree</option>
              <option>Partial</option>
              <option>Disagree</option>
            </select>
          </Field>
          <Field label="Override">
            <select aria-label="Override" className={inputClass} value={overrideValue} onChange={(event) => setOverrideValue(event.target.value as "No" | "Yes")}>
              <option>No</option>
              <option>Yes</option>
            </select>
          </Field>
        </div>

        <div className="mt-5">
          <Field label="Clinical comment">
            <textarea aria-label="Clinical comment" className={`${inputClass} min-h-28 resize-y`} value={comment} onChange={(event) => setComment(event.target.value)} />
          </Field>
        </div>

        <div className="mt-6 flex justify-end">
          <Button type="button" onClick={saveValidation} disabled={saving || !site.trim() || !clinicalCaseId.trim()}>
            <Save className="h-4 w-4" />
            {saving ? "Saving..." : "Save Validation"}
          </Button>
        </div>
      </Card>

      <div className="grid h-fit gap-5">
        <Card>
          <h2 className="mb-4 text-lg font-bold text-brand-ink">OrthoAI Output</h2>
          <dl className="grid gap-3 text-sm">
            <div className="flex items-center justify-between gap-4">
              <dt className="font-semibold text-brand-muted">AI class</dt>
              <dd className="font-bold text-brand-ink">{aiClass}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="font-semibold text-brand-muted">Confidence</dt>
              <dd className="font-bold text-brand-ink">{percent(aiConfidence)}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="font-semibold text-brand-muted">AI time</dt>
              <dd className="font-bold text-brand-ink">{seconds(aiSeconds)}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="font-semibold text-brand-muted">Model</dt>
              <dd className="font-bold text-brand-ink">{results?.model_version || "-"}</dd>
            </div>
          </dl>
        </Card>

        <Card>
          <div className="mb-4 flex items-center gap-3">
            <TableProperties className="h-5 w-5 text-brand-primary" />
            <h2 className="text-lg font-bold text-brand-ink">Validation Stats</h2>
          </div>
          <dl className="grid gap-3 text-sm">
            <div className="flex items-center justify-between gap-4">
              <dt className="font-semibold text-brand-muted">Records</dt>
              <dd className="font-bold text-brand-ink">{stats?.n ?? 0}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="font-semibold text-brand-muted">High need</dt>
              <dd className="font-bold text-brand-ink">{stats?.high_need ?? 0}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="font-semibold text-brand-muted">Class agreement</dt>
              <dd className="font-bold text-brand-ink">{stats?.class_agreement_pct == null ? "-" : `${stats.class_agreement_pct}%`}</dd>
            </div>
          </dl>
        </Card>

        <Card>
          <h2 className="mb-4 text-lg font-bold text-brand-ink">Recent Records</h2>
          <div className="grid gap-3">
            {clinicalList?.items.length ? clinicalList.items.map((item) => (
              <div key={item.id} className="rounded-app border border-brand-line bg-slate-50 p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-bold text-brand-ink">{item.case_id}</p>
                  <Pill tone={item.class_match ? "success" : "warn"}>{item.class_match ? "match" : "review"}</Pill>
                </div>
                <p className="mt-1 text-xs font-semibold text-brand-muted">{item.site} · DHC {item.dhc} · {formatDate(item.created_at)}</p>
              </div>
            )) : <p className="text-sm font-semibold text-brand-muted">No validation records for this diagnosis.</p>}
          </div>
        </Card>
      </div>
    </div>
  );
}
