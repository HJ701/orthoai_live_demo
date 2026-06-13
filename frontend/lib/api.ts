import type {
  Activity,
  CaseItem,
  CaseResults,
  ClinicalList,
  ClinicalPayload,
  ClinicalRecord,
  ClinicalStats,
  InferenceStart,
  InferenceStatus,
  OTPResponse,
  SSOProvider,
  TokenResponse,
  User,
} from "@/lib/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "https://api.demo.orthoai.co";

type ApiOptions = RequestInit & {
  token?: string;
};

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!text) return null as T;
  return JSON.parse(text) as T;
}

export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  const body = await readJson<unknown>(response).catch(() => null);
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return body as T;
}

export const authApi = {
  requestOtp: (email: string) =>
    apiFetch<OTPResponse>("/api/v1/auth/request-otp", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  login: (email: string, otp: string) =>
    apiFetch<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, otp }),
    }),
  me: (token: string) => apiFetch<User>("/api/v1/auth/me", { token }),
  acceptTerms: (token: string) =>
    apiFetch<User & { message: string }>("/api/v1/auth/accept-terms", {
      method: "PUT",
      token,
    }),
  ssoProviders: async () =>
    (await apiFetch<{ providers: SSOProvider[] }>("/api/v1/auth/sso/providers")).providers,
};

export const caseApi = {
  list: (token: string) => apiFetch<CaseItem[]>("/api/v1/cases", { token }),
  get: (token: string, caseId: number) => apiFetch<CaseItem>(`/api/v1/cases/${caseId}`, { token }),
  create: (token: string, payload: Partial<CaseItem> & { consent_checked: boolean }) =>
    apiFetch<CaseItem>("/api/v1/cases", {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  delete: (token: string, caseId: number) =>
    apiFetch<{ message: string; case_id: number }>(`/api/v1/cases/${caseId}`, {
      method: "DELETE",
      token,
    }),
  uploadImages: (token: string, caseId: number, files: File[]) => {
    const body = new FormData();
    for (const file of files) body.append("files", file);
    return apiFetch<{ image_ids: number[] }>(`/api/v1/cases/${caseId}/images`, {
      method: "POST",
      token,
      body,
    });
  },
  addNote: (token: string, caseId: number, content: string) =>
    apiFetch<{ id: number }>(`/api/v1/cases/${caseId}/notes`, {
      method: "POST",
      token,
      body: JSON.stringify({ content }),
    }),
};

export const inferenceApi = {
  start: (token: string, caseId: number) =>
    apiFetch<InferenceStart>("/api/v1/inference", {
      method: "POST",
      token,
      body: JSON.stringify({ case_id: caseId }),
    }),
  status: (token: string, jobId: number, caseId?: number) =>
    apiFetch<InferenceStatus>(
      `/api/v1/inference/${jobId}/status${caseId ? `?case_id=${caseId}` : ""}`,
      { token },
    ),
  cancel: (token: string, jobId: number, caseId?: number) =>
    apiFetch<{ message: string }>(
      `/api/v1/inference/${jobId}/cancel${caseId ? `?case_id=${caseId}` : ""}`,
      { method: "POST", token },
    ),
};

export const resultsApi = {
  get: (token: string, caseId: number) => apiFetch<CaseResults>(`/api/v1/cases/${caseId}/results`, { token }),
  pdfUrl: (caseId: number) => `${API_BASE}/api/v1/cases/${caseId}/summary.pdf`,
  downloadPdf: async (token: string, caseId: number) => {
    const response = await fetch(`${API_BASE}/api/v1/cases/${caseId}/summary.pdf`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }
    return response.blob();
  },
};

export const clinicalApi = {
  health: (token: string, caseId: number) =>
    apiFetch<{ diagnosis_complete: boolean }>(`/api/v1/clinical/health?source_case_id=${caseId}`, { token }),
  list: (token: string, caseId: number) =>
    apiFetch<ClinicalList>(`/api/v1/clinical/cases?source_case_id=${caseId}&limit=20`, { token }),
  stats: (token: string, caseId: number) =>
    apiFetch<ClinicalStats>(`/api/v1/clinical/stats?source_case_id=${caseId}`, { token }),
  create: (token: string, caseId: number, payload: ClinicalPayload) =>
    apiFetch<ClinicalRecord>(`/api/v1/clinical/cases?source_case_id=${caseId}`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
};

export const userApi = {
  activity: (token: string) => apiFetch<Activity>("/api/v1/users/activity", { token }),
};
