"use client";

import { useState } from "react";
import { ChevronDown, HelpCircle, LockKeyhole, Mail, MapPin, ShieldCheck } from "lucide-react";
import { Button, Card, cn } from "@/components/ui";

const faqs = [
  {
    question: "How do I upload images?",
    answer: "Open Upload, create a patient case using a non-identifying Patient ID/code, select PNG, JPG, or DICOM files, confirm consent and authority, then run analysis.",
  },
  {
    question: "What patient information should I include?",
    answer: "Use patient IDs or codes only. Do not include patient names, faces, or visible overlays containing Protected Health Information.",
  },
  {
    question: "How long does analysis take?",
    answer: "Inference starts after image upload and consent confirmation. Runtime depends on image count, model availability, and queue state; status and timing are shown on Results.",
  },
  {
    question: "Can I cancel an analysis?",
    answer: "Queued or running analyses can be cancelled when the backend reports the job as cancellable. Completed analyses remain available for results review.",
  },
  {
    question: "How do I download results?",
    answer: "Open the Results page for a completed case and use Download PDF Summary or export the structured JSON output for clinical records.",
  },
  {
    question: "What does the confidence score mean?",
    answer: "Confidence reflects the model score for a detected finding. It is decision support only and must be reviewed by a qualified clinician.",
  },
  {
    question: "Is this tool HIPAA/GDPR compliant?",
    answer: "The demo is designed around HIPAA/GDPR-aligned controls, including encryption, restricted access, audit logging, and UAE/GCC data residency.",
  },
  {
    question: "Can I share results with colleagues?",
    answer: "Share only according to your clinic policy and patient consent. Avoid moving identifiable patient data into unsupported channels.",
  },
];

export default function HelpPage() {
  const [open, setOpen] = useState(0);
  const mailto = "mailto:Info@orthoai.co?subject=OrthoAI%20Demo%20Support";

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Help & Support</h1>
        <p className="mt-2 text-slate-600">Find answers to common questions and learn how to use the Medical AI Diagnostic Assistant</p>
      </div>

      <Card className="p-8">
        <div className="mb-5 flex items-center gap-3">
          <HelpCircle className="h-6 w-6 text-brand-primary" />
          <h2 className="text-xl font-semibold text-slate-900">Frequently Asked Questions</h2>
        </div>
        <div className="divide-y divide-brand-line">
          {faqs.map((item, index) => (
            <section key={item.question} className="py-4">
              <button
                type="button"
                onClick={() => setOpen(open === index ? -1 : index)}
                className="flex w-full items-center justify-between gap-4 text-left text-base font-medium text-slate-900"
              >
                {item.question}
                <ChevronDown className={cn("h-5 w-5 text-slate-500 transition", open === index && "rotate-180")} />
              </button>
              {open === index ? <p className="mt-3 text-sm leading-6 text-slate-600">{item.answer}</p> : null}
            </section>
          ))}
        </div>
      </Card>

      <Card className="p-8">
        <div className="mb-5 flex items-center gap-3">
          <ShieldCheck className="h-6 w-6 text-brand-primary" />
          <h2 className="text-xl font-semibold text-slate-900">Privacy & Security</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-2xl bg-white p-4">
            <MapPin className="mb-3 h-6 w-6 text-brand-primary" />
            <h3 className="font-semibold text-slate-900">Data Residency</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">All data is processed and stored within the UAE/GCC region in compliance with local data residency requirements.</p>
          </div>
          <div className="rounded-2xl bg-white p-4">
            <LockKeyhole className="mb-3 h-6 w-6 text-brand-primary" />
            <h3 className="font-semibold text-slate-900">Encryption</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">All data is encrypted at rest and in transit using industry-standard encryption protocols.</p>
          </div>
          <div className="rounded-2xl bg-white p-4">
            <ShieldCheck className="mb-3 h-6 w-6 text-brand-primary" />
            <h3 className="font-semibold text-slate-900">Access Control</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">Access is restricted to authorized clinicians only. All actions are logged in the audit trail.</p>
          </div>
        </div>
      </Card>

      <Card className="flex flex-wrap items-center justify-between gap-4 p-8">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Need additional support?</h2>
          <p className="mt-2 text-sm text-slate-600">Contact the OrthoAI support team for demo access, workflow questions, or technical assistance.</p>
        </div>
        <a href={mailto}>
          <Button type="button">
            <Mail className="h-4 w-4" />
            Contact Support
          </Button>
        </a>
      </Card>
    </div>
  );
}
