import type { Metadata } from "next";
import type { ReactNode } from "react";
import { ClientRoot } from "@/components/client-root";
import "./globals.css";

export const metadata: Metadata = {
  title: "Medical AI - Clinical Diagnostic Assistant",
  description: "AI-powered dental diagnostic tool for clinicians",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <ClientRoot>{children}</ClientRoot>
      </body>
    </html>
  );
}
