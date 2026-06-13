"use client";

import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { authApi } from "@/lib/api";
import { clearSession, getToken } from "@/lib/session";
import type { User } from "@/lib/types";
import { LoadingPanel } from "@/components/ui";

const PUBLIC_ROUTES = new Set(["/signin", "/help"]);

export function AuthGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      if (PUBLIC_ROUTES.has(pathname || "")) {
        setReady(true);
        return;
      }
      const token = getToken();
      if (!token) {
        router.replace("/signin");
        return;
      }
      try {
        const user: User = await authApi.me(token);
        if (!user.terms_accepted && pathname !== "/terms") {
          router.replace("/terms");
          return;
        }
        if (!cancelled) setReady(true);
      } catch {
        clearSession();
        router.replace("/signin");
      }
    }
    void check();
    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  if (!ready) {
    return (
      <main className="animated-bg min-h-screen p-6">
        <LoadingPanel />
      </main>
    );
  }
  return children;
}
