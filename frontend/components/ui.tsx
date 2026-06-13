import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function Button({
  className,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
}) {
  return (
    <button
      className={cn(
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-xl px-6 py-2.5 text-sm font-medium transition focus:outline-none focus:ring-4 disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "gradient-purple text-white shadow-sm hover:brightness-95 focus:ring-indigo-200",
        variant === "secondary" && "border border-brand-primary bg-white text-brand-primary hover:bg-indigo-50 focus:ring-indigo-100",
        variant === "danger" && "bg-red-600 text-white hover:bg-red-700 focus:ring-red-200",
        variant === "ghost" && "bg-transparent text-brand-muted hover:bg-slate-100 focus:ring-slate-200",
        className,
      )}
      {...props}
    />
  );
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <section className={cn("glass-panel rounded-app p-6", className)} {...props} />;
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="grid gap-2 text-sm font-semibold text-slate-700">
      <span>{label}</span>
      {children}
      {hint ? <span className="text-xs font-medium text-brand-muted">{hint}</span> : null}
    </label>
  );
}

export const inputClass =
  "min-h-14 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm text-brand-ink outline-none transition placeholder:text-slate-500 focus:border-brand-primary focus:ring-4 focus:ring-indigo-100";

export function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: "info" | "warn" | "error" | "success";
}) {
  return (
    <div
      className={cn(
        "rounded-lg border px-4 py-3 text-sm font-semibold",
        tone === "info" && "border-indigo-200 bg-indigo-50 text-indigo-800",
        tone === "warn" && "border-amber-200 bg-amber-50 text-amber-800",
        tone === "error" && "border-red-200 bg-red-50 text-red-700",
        tone === "success" && "border-emerald-200 bg-emerald-50 text-emerald-700",
      )}
    >
      {children}
    </div>
  );
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warn" | "error" | "primary";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-bold capitalize",
        tone === "neutral" && "bg-slate-100 text-slate-600",
        tone === "success" && "bg-emerald-100 text-emerald-700",
        tone === "warn" && "bg-amber-100 text-amber-700",
        tone === "error" && "bg-red-100 text-red-700",
        tone === "primary" && "bg-indigo-100 text-brand-primary",
      )}
    >
      {children}
    </span>
  );
}

export function LoadingPanel({ label = "Loading..." }: { label?: string }) {
  return (
    <Card className="flex min-h-48 items-center justify-center">
      <div className="flex items-center gap-3 text-sm font-semibold text-brand-muted">
        <span className="h-3 w-3 animate-pulse rounded-full bg-brand-primary" />
        {label}
      </div>
    </Card>
  );
}
