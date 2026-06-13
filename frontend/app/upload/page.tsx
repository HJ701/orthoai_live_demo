"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import type { DragEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, CloudUpload, Plus, PlayCircle, Trash2 } from "lucide-react";
import { caseApi, inferenceApi } from "@/lib/api";
import { getToken, setCurrentCaseId } from "@/lib/session";
import type { CaseItem } from "@/lib/types";
import { Button, Card, Notice, cn, inputClass } from "@/components/ui";

const modalityOptions = [
  "RGB Intra-oral",
  "RGB Extra-oral",
  "OPG (Panoramic)",
  "Panoramic X-ray",
  "Cephalometric",
  "X-ray Cephalometric",
  "CBCT",
  "Other",
];

type SelectedImage = {
  id: string;
  file: File;
  previewUrl: string;
  modality: string;
};

function imageId(file: File): string {
  return `${file.name}-${file.size}-${file.lastModified}-${crypto.randomUUID()}`;
}

function fileSize(size: number): string {
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(2)} MB`;
}

function hasImagePreview(file: File): boolean {
  return file.type.startsWith("image/") && !file.name.toLowerCase().endsWith(".dcm");
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const imagesRef = useRef<SelectedImage[]>([]);
  const [patientId, setPatientId] = useState("");
  const [title, setTitle] = useState("");
  const [clinicLocation, setClinicLocation] = useState("");
  const [selectedModalities, setSelectedModalities] = useState<string[]>([]);
  const [modalityMenuOpen, setModalityMenuOpen] = useState(false);
  const [note, setNote] = useState("");
  const [consent, setConsent] = useState(false);
  const [images, setImages] = useState<SelectedImage[]>([]);
  const [caseItem, setCaseItem] = useState<CaseItem | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    imagesRef.current = images;
  }, [images]);

  useEffect(() => () => {
    for (const image of imagesRef.current) {
      if (image.previewUrl) URL.revokeObjectURL(image.previewUrl);
    }
  }, []);

  function addFiles(fileList: FileList | File[]) {
    const incoming = Array.from(fileList).filter((file) => file.type.startsWith("image/") || file.name.toLowerCase().endsWith(".dcm"));
    if (incoming.length === 0) return;
    setImages((current) => [
      ...current,
      ...incoming.map((file) => ({
        id: imageId(file),
        file,
        previewUrl: hasImagePreview(file) ? URL.createObjectURL(file) : "",
        modality: selectedModalities[0] || "RGB Intra-oral",
      })),
    ]);
    setUploadMessage(`${incoming.length} file${incoming.length === 1 ? "" : "s"} selected and ready for secure upload.`);
    setError("");
  }

  function removeImage(id: string) {
    setImages((current) => {
      const target = current.find((image) => image.id === id);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return current.filter((image) => image.id !== id);
    });
  }

  function setImageModality(id: string, modality: string) {
    setImages((current) => current.map((image) => (image.id === id ? { ...image, modality } : image)));
  }

  function toggleModality(modality: string) {
    setSelectedModalities((current) => {
      const next = current.includes(modality) ? current.filter((item) => item !== modality) : [...current, modality];
      return next;
    });
  }

  function dragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(true);
  }

  function dropFiles(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
    addFiles(event.dataTransfer.files);
  }

  async function runAnalysis() {
    const token = getToken();
    if (!token) {
      router.replace("/signin");
      return;
    }
    if (!consent) {
      setError("Consent and authority must be confirmed before running analysis.");
      return;
    }
    if (images.length === 0) {
      setError("Upload at least one clinical image before running analysis.");
      return;
    }

    setBusy(true);
    setError("");
    setUploadMessage(`Uploading ${images.length} clinical image${images.length === 1 ? "" : "s"} securely...`);

    try {
      const modalities = unique([...selectedModalities, ...images.map((image) => image.modality)]);
      const created = await caseApi.create(token, {
        consent_checked: consent,
        patient_id: patientId.trim() || undefined,
        title: title.trim() || undefined,
        clinic_location: clinicLocation.trim() || undefined,
        tags: modalities,
        note: note.trim() || undefined,
      });
      setCaseItem(created);
      setCurrentCaseId(created.id);

      await caseApi.uploadImages(token, created.id, images.map((image) => image.file));
      setUploadMessage("Images uploaded successfully. OrthoAI analysis is starting...");
      const job = await inferenceApi.start(token, created.id);
      router.push(`/inference?case_id=${created.id}&job_id=${job.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to run analysis.");
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-7">
      <div>
        <h1 className="text-4xl font-normal tracking-normal text-slate-900">Create Patient Case</h1>
        <p className="mt-2 text-lg text-slate-600">Create a new case and upload clinical images for AI analysis</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[0.95fr_1.35fr]">
        <Card className="bg-white/95 p-7">
          <h2 className="mb-4 text-2xl font-normal text-slate-800">Case Information</h2>
          <div className="grid gap-6">
            <div>
              <input
                aria-label="Patient reference"
                className={inputClass}
                value={patientId}
                onChange={(event) => setPatientId(event.target.value)}
                placeholder="Patient ID/Code (Optional)"
              />
              <span className="mt-1 block text-xs font-medium text-slate-600">No PHI names - use ID/code only</span>
            </div>
            <input
              aria-label="Case title"
              className={inputClass}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Case Title (Optional)"
            />

            <div className="relative">
              <button
                type="button"
                aria-label="Modality Tags"
                onClick={() => setModalityMenuOpen((open) => !open)}
                className={`${inputClass} flex items-center justify-between text-left`}
              >
                <span className="flex flex-wrap gap-2">
                  {selectedModalities.length ? selectedModalities.map((modality) => (
                    <span key={modality} className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-800">{modality}</span>
                  )) : <span className="text-slate-500">Modality Tags (Optional)</span>}
                </span>
                <ChevronDown className="h-5 w-5 shrink-0 text-slate-500" />
              </button>
              {modalityMenuOpen ? (
                <div className="absolute left-0 right-0 top-[calc(100%+8px)] z-20 overflow-hidden rounded-2xl bg-white py-2 shadow-2xl ring-1 ring-slate-200">
                  {modalityOptions.map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => toggleModality(option)}
                      className={cn(
                        "flex w-full items-center justify-between px-5 py-3 text-left text-base hover:bg-slate-50",
                        selectedModalities.includes(option) && "bg-slate-100 font-semibold",
                      )}
                    >
                      {option}
                      {selectedModalities.includes(option) ? <span className="text-brand-primary">Selected</span> : null}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            <input
              aria-label="Clinic location"
              className={inputClass}
              value={clinicLocation}
              onChange={(event) => setClinicLocation(event.target.value)}
              placeholder="Clinic Location (Optional)"
            />
            <textarea
              aria-label="Clinical note"
              className={`${inputClass} min-h-44 resize-y`}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Notes (Optional)"
            />
          </div>
        </Card>

        <div className="grid gap-6">
          <Card className="bg-white/95 p-7">
            <div className="mb-6 flex items-center justify-between gap-4">
              <div>
                <h2 className="text-2xl font-normal text-slate-800">Add Images</h2>
                {images.length ? <p className="mt-4 text-base text-slate-600">{images.length} file{images.length === 1 ? "" : "s"} selected</p> : null}
              </div>
              {images.length ? (
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-brand-primary hover:bg-indigo-50"
                >
                  <Plus className="h-5 w-5" />
                  Add More
                </button>
              ) : null}
            </div>

            {images.length === 0 ? (
              <label
                className={cn(
                  "grid min-h-[360px] cursor-pointer place-items-center rounded-app bg-white p-10 text-center transition",
                  isDragging && "ring-4 ring-indigo-200",
                )}
                onDragOver={dragOver}
                onDragLeave={() => setIsDragging(false)}
                onDrop={dropFiles}
              >
                <div>
                  <CloudUpload className="mx-auto mb-8 h-20 w-20 text-brand-primary" />
                  <p className="text-xl text-slate-600">{isDragging ? "Release to add images" : "Drop images here to begin"}</p>
                  <p className="mt-2 text-base text-slate-500">or click to browse</p>
                  <span className="gradient-purple mt-8 inline-flex rounded-full px-10 py-4 text-base font-medium text-white shadow-sm">
                    Select Files
                  </span>
                  <p className="mt-6 text-sm text-slate-500">Supported: PNG, JPG, DICOM | Max 10MB per file</p>
                </div>
                <input
                  ref={inputRef}
                  aria-label="Clinical image files"
                  className="sr-only"
                  type="file"
                  accept="image/*,.dcm"
                  multiple
                  onChange={(event) => {
                    addFiles(event.target.files || []);
                    event.target.value = "";
                  }}
                />
              </label>
            ) : (
              <div className="grid max-h-[680px] gap-5 overflow-y-auto pr-2">
                <input
                  ref={inputRef}
                  aria-label="Clinical image files"
                  className="sr-only"
                  type="file"
                  accept="image/*,.dcm"
                  multiple
                  onChange={(event) => {
                    addFiles(event.target.files || []);
                    event.target.value = "";
                  }}
                />
                {images.map((image) => (
                  <article key={image.id} className="grid grid-cols-[96px_1fr_auto] items-center gap-5 rounded-[32px] bg-indigo-50/60 p-6">
                    <div className="relative h-24 w-24 overflow-hidden rounded-2xl bg-slate-200">
                      {image.previewUrl ? (
                        <Image src={image.previewUrl} alt={image.file.name} fill sizes="96px" className="object-cover" unoptimized />
                      ) : (
                        <div className="grid h-full place-items-center text-xs font-semibold text-slate-500">DICOM</div>
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-lg font-medium text-slate-900">{image.file.name}</p>
                      <p className="mt-1 text-sm text-slate-500">{fileSize(image.file.size)}</p>
                      <select
                        aria-label={`Modality for ${image.file.name}`}
                        className="mt-4 min-h-12 w-full rounded-2xl border border-slate-300 bg-white px-4 text-base text-slate-900 outline-none focus:border-brand-primary focus:ring-4 focus:ring-indigo-100"
                        value={image.modality}
                        onChange={(event) => setImageModality(image.id, event.target.value)}
                      >
                        {modalityOptions.map((option) => <option key={option}>{option}</option>)}
                      </select>
                    </div>
                    <button
                      type="button"
                      aria-label={`Remove ${image.file.name}`}
                      onClick={() => removeImage(image.id)}
                      className="rounded-full p-3 text-red-500 hover:bg-red-50"
                    >
                      <Trash2 className="h-6 w-6" />
                    </button>
                  </article>
                ))}
              </div>
            )}
          </Card>

          <Card className="bg-white/95 p-6">
            <label className="flex cursor-pointer items-start gap-4 text-sm text-slate-800">
              <input
                aria-label="Consent confirmation"
                className="mt-1 h-5 w-5 accent-brand-primary"
                type="checkbox"
                checked={consent}
                onChange={(event) => setConsent(event.target.checked)}
              />
              <span>
                <span className="block font-medium">I confirm I have consent and authority to upload these clinical images.</span>
                <span className="mt-2 block text-sm text-slate-500">
                  No names/faces; anonymize overlays if needed. PHI reminder: Ensure all patient identifiers are removed.
                </span>
              </span>
            </label>
          </Card>

          {uploadMessage ? <Notice tone="success">{uploadMessage}</Notice> : null}
          {error ? <Notice tone="error">{error}</Notice> : null}
          {caseItem ? <Notice tone="info">Case #{caseItem.id} created. Preparing inference workflow...</Notice> : null}

          <div className="flex justify-end">
            <Button type="button" className="min-w-56 rounded-full py-4 text-base" onClick={runAnalysis} disabled={busy || !consent || images.length === 0}>
              <PlayCircle className="h-4 w-4" />
              {busy ? "Uploading..." : "Run Analysis"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
