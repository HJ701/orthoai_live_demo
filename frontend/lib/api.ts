// API Client for OrthoAI Backend

// Base URL for the FastAPI backend. Configured at build time via
// NEXT_PUBLIC_API_BASE_URL (set per-environment, e.g. http://127.0.0.1:8000
// for local dev). Falls back to the production API so a missing env var never
// produces "undefined/api/..." request URLs.
const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.demo.orthoai.co'
).replace(/\/$/, '')

// Types matching backend schemas
export interface Token {
  access_token: string
  token_type: string
}

export interface OTPRequest {
  email: string
}

export interface OTPResponse {
  message: string
  // Only returned by the backend in development mode (DEV_EXPOSE_OTP=true),
  // where no email is actually sent. Never present in production responses.
  dev_otp?: string | null
}

export interface OTPLogin {
  email: string
  otp: string
}

export interface CaseCreate {
  consent_checked: boolean
  patient_id?: string
  title?: string
  clinic_location?: string
  tags?: string[]
  note?: string
}

export interface CaseResponse {
  id: number
  user_id: number
  consent_checked: boolean
  patient_id: string
  title: string
  clinic_location?: string
  note?: string
  tags?: string[]
  status?: 'queued' | 'running' | 'done' | 'error'
  created_at: string
}

export interface ImageUploadResponse {
  image_ids: number[]
}

export interface UploadImage {
  file: File
  modality?: string
}

// Map a UI modality label to a filename prefix the backend recognises as an
// X-ray. RGB / Other get no prefix (treated as RGB intra-oral).
function modalityFilenamePrefix(modality?: string): string {
  const m = (modality || '').toLowerCase()
  if (m.includes('opg') || m.includes('panoramic')) return 'opg_'
  if (m.includes('ceph')) return 'ceph_'
  if (m.includes('cbct')) return 'xray_'
  return ''
}

export interface InferenceRequest {
  case_id: number
}

export interface InferenceResponse {
  job_id: number
}

export type JobState = 'queued' | 'running' | 'done' | 'error'

export interface InferenceStatusResponse {
  state: JobState
  progress: number
  error_message?: string | null
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

export interface ImageEvidenceResponse {
  image_id: number
  filename: string
  findings: Record<string, any>
  confidence: number
}

export interface CaseResultsResponse {
  case_id: number
  model_version: string
  findings: Record<string, any>
  summary: string
  confidences: Record<string, number>
  per_image_evidence: ImageEvidenceResponse[]
  created_at: string
}

export interface CaseNoteCreate {
  content: string
}

export interface CaseNoteResponse {
  id: number
  case_id: number
  content: string
  created_by: number
  created_at: string
}

// Helper function to get auth token from storage
function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null
  return sessionStorage.getItem('authToken')
}

// Helper function to set auth token
function setAuthToken(token: string): void {
  if (typeof window === 'undefined') return
  sessionStorage.setItem('authToken', token)
}

// Helper function to clear auth token
export function clearAuthToken(): void {
  if (typeof window === 'undefined') return
  sessionStorage.removeItem('authToken')
}

// Base fetch wrapper with auth
async function apiFetch(
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = getAuthToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    // Unauthorized - clear token and redirect to signin
    clearAuthToken()
    if (typeof window !== 'undefined') {
      window.location.href = '/signin'
    }
    throw new Error('Unauthorized')
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `API error: ${response.statusText}`)
  }

  return response
}

// Auth API
export const authAPI = {
  async requestOTP(email: string): Promise<OTPResponse> {
    const response = await apiFetch('/api/v1/auth/request-otp', {
      method: 'POST',
      body: JSON.stringify({ email }),
    })
    return response.json()
  },

  async login(email: string, otp: string): Promise<Token> {
    const response = await apiFetch('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, otp }),
    })
    const token = await response.json()
    setAuthToken(token.access_token)
    return token
  },

  async me(): Promise<User> {
    const response = await apiFetch('/api/v1/auth/me', { method: 'GET' })
    return response.json()
  },
}

// Cases API
export const casesAPI = {
  async createCase(data: CaseCreate): Promise<CaseResponse> {
    const response = await apiFetch('/api/v1/cases', {
      method: 'POST',
      body: JSON.stringify(data),
    })
    return response.json()
  },

  async uploadImages(
    caseId: number,
    files: UploadImage[]
  ): Promise<ImageUploadResponse> {
    const formData = new FormData()
    files.forEach(({ file, modality }) => {
      // The backend infers modality from the filename (opg/panoramic/xray/ceph
      // => X-ray, else RGB). Encode the user-selected modality as a prefix so
      // the dropdown choice actually drives classification.
      const prefix = modalityFilenamePrefix(modality)
      const name = prefix && !file.name.toLowerCase().startsWith(prefix)
        ? `${prefix}${file.name}`
        : file.name
      formData.append('files', file, name)
    })

    const token = getAuthToken()
    const headers: Record<string, string> = {}
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const response = await fetch(
      `${API_BASE_URL}/api/v1/cases/${caseId}/images`,
      {
        method: 'POST',
        headers,
        body: formData,
      }
    )

    if (response.status === 401) {
      clearAuthToken()
      if (typeof window !== 'undefined') {
        window.location.href = '/signin'
      }
      throw new Error('Unauthorized')
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(error.detail || `API error: ${response.statusText}`)
    }

    return response.json()
  },

  async addNote(caseId: number, content: string): Promise<CaseNoteResponse> {
    const response = await apiFetch(`/api/v1/cases/${caseId}/notes`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    })
    return response.json()
  },

  async listCases(): Promise<CaseResponse[]> {
    const response = await apiFetch('/api/v1/cases', {
      method: 'GET',
    })
    return response.json()
  },

  async getCase(caseId: number): Promise<CaseResponse> {
    const response = await apiFetch(`/api/v1/cases/${caseId}`, { method: 'GET' })
    return response.json()
  },
}

// Inference API
export const inferenceAPI = {
  async startInference(caseId: number): Promise<InferenceResponse> {
    const response = await apiFetch('/api/v1/inference', {
      method: 'POST',
      body: JSON.stringify({ case_id: caseId }),
    })
    return response.json()
  },

  async getStatus(jobId: number): Promise<InferenceStatusResponse> {
    const response = await apiFetch(`/api/v1/inference/${jobId}/status`, {
      method: 'GET',
    })
    return response.json()
  },

  async cancelJob(jobId: number): Promise<void> {
    await apiFetch(`/api/v1/inference/${jobId}/cancel`, {
      method: 'POST',
    })
  },
}

// Results API
export const resultsAPI = {
  async getResults(caseId: number): Promise<CaseResultsResponse> {
    const response = await apiFetch(`/api/v1/cases/${caseId}/results`, {
      method: 'GET',
    })
    return response.json()
  },

  async downloadPDF(caseId: number): Promise<Blob> {
    const token = getAuthToken()
    const headers: HeadersInit = {}
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const response = await fetch(
      `${API_BASE_URL}/api/v1/cases/${caseId}/summary.pdf`,
      {
        headers,
      }
    )

    if (response.status === 401) {
      clearAuthToken()
      if (typeof window !== 'undefined') {
        window.location.href = '/signin'
      }
      throw new Error('Unauthorized')
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(error.detail || `API error: ${response.statusText}`)
    }

    return response.blob()
  },
}

// ===================== User profile & activity =====================

export interface User {
  id: number
  email: string
  auth_provider: string
  full_name?: string | null
  avatar_url?: string | null
  is_active: boolean
  terms_accepted: boolean
  terms_accepted_at?: string | null
  last_login_at?: string | null
  created_at: string
}

export interface ActivityCase {
  id: number
  patient_id: string | null
  title: string | null
  status: JobState | null
  has_results: boolean
  created_at: string
}

export interface ActivityValidation {
  id: number
  orthoai_case_id: number
  site: string
  case_id: string
  m_class: string
  dhc: number
  ai_class: string | null
  ai_dhc: number | null
  class_match: boolean | null
  created_at: string
}

export interface AuditLogEntry {
  id: number
  action: string
  resource_type: string
  resource_id: number | null
  details: Record<string, any>
  ip_address: string | null
  created_at: string
}

export interface Activity {
  user: User
  case_count: number
  completed_diagnoses: number
  clinical_validation_count: number
  cases: ActivityCase[]
  clinical_validations: ActivityValidation[]
  audit_logs: AuditLogEntry[]
}

export const usersAPI = {
  async activity(): Promise<Activity> {
    const response = await apiFetch('/api/v1/users/activity', { method: 'GET' })
    return response.json()
  },
}

// ===================== Clinical validation =====================

export interface ClinicalPayload {
  site: string
  case_id: string
  assess_date?: string | null
  clinician?: string | null
  age?: number | null
  sex?: 'Female' | 'Male' | 'Other' | 'Undisclosed' | null
  rec_opg: boolean
  rec_photo: boolean
  rec_other: boolean
  m_class: string
  dhc: number
  ac?: number | null
  t_manual?: number | null
  ai_class?: string | null
  ai_dhc?: number | null
  ai_ac?: number | null
  ai_conf?: number | null
  t_ai?: number | null
  calib?: 'Well-calibrated' | 'Over-confident' | 'Under-confident' | 'N/A' | null
  agree?: 'Agree' | 'Partial' | 'Disagree' | null
  override?: 'Yes' | 'No' | null
  override_reason?: string | null
  useful?: number | null
  comment?: string | null
}

export interface ClinicalRecord {
  id: number
  orthoai_case_id: number
  site: string
  case_id: string
  m_class: string
  dhc: number
  ai_class: string | null
  ai_dhc: number | null
  ai_ac?: number | null
  ai_conf?: number | null
  agree?: string | null
  override?: string | null
  class_match: boolean | null
  useful: number | null
  high_need?: boolean
  dhc_delta?: number | null
  created_at: string
}

export interface ClinicalList {
  total: number
  items: ClinicalRecord[]
}

export interface ClinicalHealth {
  status: string
  authenticated: boolean
  diagnosis_required: boolean
  diagnosis_complete: boolean
}

export interface ClinicalStats {
  n: number
  sites: number
  high_need: number
  class_pairs: number
  class_agreement_pct: number | null
  dhc_pairs: number
  dhc_exact_pct: number | null
  mean_dhc_delta: number | null
  mean_useful: number | null
  override_rate_pct: number | null
  mean_t_manual: number | null
  mean_t_ai: number | null
}

export const clinicalAPI = {
  async health(caseId: number): Promise<ClinicalHealth> {
    const response = await apiFetch(`/api/v1/clinical/health?source_case_id=${caseId}`, {
      method: 'GET',
    })
    return response.json()
  },

  async list(caseId: number): Promise<ClinicalList> {
    const response = await apiFetch(
      `/api/v1/clinical/cases?source_case_id=${caseId}&limit=20`,
      { method: 'GET' },
    )
    return response.json()
  },

  async stats(caseId: number): Promise<ClinicalStats> {
    const response = await apiFetch(`/api/v1/clinical/stats?source_case_id=${caseId}`, {
      method: 'GET',
    })
    return response.json()
  },

  async create(caseId: number, payload: ClinicalPayload): Promise<ClinicalRecord> {
    const response = await apiFetch(`/api/v1/clinical/cases?source_case_id=${caseId}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    return response.json()
  },
}

