"use client";

const TOKEN_KEYS = ["orthoai_access_token", "authToken", "access_token"];

export function getToken(): string {
  if (typeof window === "undefined") return "";
  for (const store of [window.sessionStorage, window.localStorage]) {
    for (const key of TOKEN_KEYS) {
      const value = store.getItem(key);
      if (value) return value.replace(/^Bearer\s+/i, "");
    }
  }
  return "";
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  for (const key of TOKEN_KEYS) {
    window.sessionStorage.setItem(key, token);
    window.localStorage.setItem(key, token);
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  for (const key of TOKEN_KEYS) {
    window.sessionStorage.removeItem(key);
    window.localStorage.removeItem(key);
  }
  window.sessionStorage.removeItem("orthoai_current_case_id");
  window.localStorage.removeItem("orthoai_current_case_id");
}

export function setCurrentCaseId(caseId: number): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem("orthoai_current_case_id", String(caseId));
  window.localStorage.setItem("orthoai_current_case_id", String(caseId));
}

export function getCurrentCaseId(): string {
  if (typeof window === "undefined") return "";
  return (
    window.sessionStorage.getItem("orthoai_current_case_id") ||
    window.localStorage.getItem("orthoai_current_case_id") ||
    ""
  );
}
