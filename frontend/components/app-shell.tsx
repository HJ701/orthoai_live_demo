"use client";

import Image from "next/image";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";
import { motion } from "framer-motion";
import {
  CircleHelp,
  FolderOpen,
  LogOut,
  Stethoscope,
  Upload,
  UserCircle,
} from "lucide-react";
import { clearSession, getCurrentCaseId } from "@/lib/session";
import { Button, cn } from "@/components/ui";

const nav = [
  { label: "Upload", href: "/upload", icon: Upload },
  { label: "Clinical Validation", href: "/clinical", icon: Stethoscope },
  { label: "Cases", href: "/cases", icon: FolderOpen },
  { label: "Help", href: "/help", icon: CircleHelp },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const params = useSearchParams();
  const isAuthPage = pathname === "/signin" || pathname === "/terms";

  if (isAuthPage) return <>{children}</>;

  function goClinical() {
    const caseId = params.get("case_id") || getCurrentCaseId();
    router.push(caseId ? `/clinical?case_id=${encodeURIComponent(caseId)}` : "/clinical");
  }

  return (
    <div className="animated-bg flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-brand-line bg-white">
        <div className="mx-auto flex min-h-16 max-w-none items-center justify-between gap-4 px-6 md:px-8">
          <button
            type="button"
            onClick={() => router.push("/upload")}
            className="flex h-11 items-center gap-3"
            aria-label="OrthoAI upload"
          >
            <Image src="/header.png" alt="OrthoAI" width={120} height={40} priority className="h-auto max-h-10 w-auto" />
          </button>
          <nav className="flex flex-1 items-center justify-end gap-1 overflow-x-auto">
            {nav.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              return (
                <button
                  key={item.href}
                  type="button"
                  onClick={() => (item.href === "/clinical" ? goClinical() : router.push(item.href))}
                  className={cn(
                    "inline-flex min-h-10 items-center gap-2 rounded-xl px-3 text-sm font-medium whitespace-nowrap transition",
                    active ? "bg-indigo-50 text-brand-primary" : "text-brand-muted hover:bg-indigo-50",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </button>
              );
            })}
            <Button variant="ghost" className="px-3" onClick={() => router.push("/account")} aria-label="Account and audit">
              <UserCircle className="h-5 w-5" />
            </Button>
            <Button
              variant="ghost"
              className="px-3"
              onClick={() => {
                clearSession();
                router.push("/signin");
              }}
              aria-label="Sign out"
            >
              <LogOut className="h-5 w-5" />
            </Button>
          </nav>
        </div>
      </header>
      <motion.main
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.28, ease: "easeOut" }}
        className="mx-auto grid w-full max-w-6xl flex-1 gap-6 px-4 py-12 md:px-8"
      >
        {children}
      </motion.main>
      <footer className="border-t border-brand-line bg-slate-50 px-4 py-6 text-center text-xs font-medium text-brand-muted">
        <p>⚠️ For decision support only; not a standalone diagnostic tool.</p>
        <p className="mt-1 text-slate-400">Model version: v1.0.0 | Data residency: UAE/GCC | Privacy Policy</p>
      </footer>
    </div>
  );
}
