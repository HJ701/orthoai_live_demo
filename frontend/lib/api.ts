// API Client for OrthoAI Backend

// Base URL for the FastAPI backend. Configured at build time via
// NEXT_PUBLIC_API_BASE_URL (set per-environment, e.g. http://127.0.0.1:8000
// for local dev). Falls back to the production API so a missing env var never
// produces "undefined/api/..." request URLs.
const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.demo.orthoai.co'
).replace(/\/$/, '')

// UX review mode keeps every interaction inside the browser. No request is
// made to FastAPI (or to any other remote service) when this flag is enabled.
export const IS_UI_ONLY_DEMO =
  process.env.NEXT_PUBLIC_UI_ONLY_DEMO === 'true'

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

export interface ExplanationResponse {
  case_id: number
  explanation: string
  source: 'openai' | 'fallback'
  model_version: string
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

  const response = IS_UI_ONLY_DEMO
    ? await demoApiFetch(endpoint, { ...options, headers })
    : await fetch(`${API_BASE_URL}${endpoint}`, {
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

  async acceptTerms(): Promise<User> {
    const response = await apiFetch('/api/v1/auth/accept-terms', {
      method: 'PUT',
      body: JSON.stringify({}),
    })
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
    if (IS_UI_ONLY_DEMO) {
      return demoUploadImages(caseId, files)
    }

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

  // Fetch an uploaded image (auth-protected) and return an object URL for <img>.
  async getImageObjectUrl(caseId: number, imageId: number): Promise<string> {
    if (IS_UI_ONLY_DEMO) {
      return URL.createObjectURL(demoImageBlob(caseId, imageId))
    }

    const token = getAuthToken()
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    const response = await fetch(
      `${API_BASE_URL}/api/v1/cases/${caseId}/images/${imageId}`,
      { headers },
    )
    if (!response.ok) throw new Error(`Failed to load image ${imageId}: ${response.status}`)
    return URL.createObjectURL(await response.blob())
  },
}

// Inference API
export const inferenceAPI = {
  async startInference(
    caseId: number,
    options?: { forceRerun?: boolean },
  ): Promise<InferenceResponse> {
    const response = await apiFetch('/api/v1/inference', {
      method: 'POST',
      body: JSON.stringify({
        case_id: caseId,
        force_rerun: options?.forceRerun || false,
      }),
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

  async getExplanation(caseId: number): Promise<ExplanationResponse> {
    const response = await apiFetch(`/api/v1/cases/${caseId}/explanation`, {
      method: 'GET',
    })
    return response.json()
  },

  async downloadPDF(caseId: number): Promise<Blob> {
    if (IS_UI_ONLY_DEMO) {
      return new Blob(
        [
          `OrthoAI UI preview\n\nCase ${caseId}\nThis browser-only preview does not generate a clinical report.`,
        ],
        { type: 'application/pdf' },
      )
    }

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

// ===================== Research Mode v3 =====================

export type ResearchRole =
  | 'clinician'
  | 'reviewer'
  | 'adjudicator'
  | 'research_admin'

export type ResearchEpisodeState =
  | 'pre_ai'
  | 'pre_ai_locked'
  | 'ai_revealed'
  | 'final_locked'
  | 'adjudicated'
  | 'withdrawn'

export interface ResearchParticipant {
  id: number
  study_code: string
  site_code: string
  participant_code: string
  role: ResearchRole
  specialty?: string | null
  experience_band?: string | null
  consent_version: string
  consented_at: string
  withdrawn_at?: string | null
  is_active: boolean
}

export interface ResearchContext {
  enabled: boolean
  participant?: ResearchParticipant | null
  study_status?: 'draft' | 'active' | 'paused' | 'closed' | null
  protocol_version?: string | null
  consent_version?: string | null
  active_epoch_code?: string | null
  ui_version: string
}

export interface ResearchDecisionRecord {
  id: number
  task_schema_version: string
  decision: Record<string, any>
  confidence: number
  client_active_seconds?: number | null
  server_elapsed_seconds: number
  submitted_at: string
  content_sha256: string
}

export interface ResearchAIReveal {
  id: number
  model_version: string
  model_artifact_sha256?: string | null
  result_schema_version: string
  ui_version: string
  payload: CaseResultsResponse
  payload_sha256: string
  provenance?: Record<string, any> | null
  inference_created_at: string
  revealed_at: string
}

export interface ResearchFinalDecision extends ResearchDecisionRecord {
  agreement?: 'agree' | 'partial' | 'disagree' | null
  override?: boolean | null
  override_reason?: string | null
  usefulness?: number | null
}

export interface ResearchFollowUpPlan {
  required: boolean
  kind: 'none' | 'reason' | 'pulse' | 'reason_and_pulse'
  triggers: string[]
  instrument_code: string
  instrument_version: string
  period_code?: string | null
  completed: boolean
}

export interface ResearchEpisode {
  id: number
  study_code: string
  site_code: string
  epoch_code: string
  participant_code: string
  case_id: number
  state: ResearchEpisodeState
  condition_code?: string | null
  exposure_index: number
  attempt_index: number
  repeat_of_episode_id?: number | null
  last_event_sequence: number
  pre_ai_started_at: string
  pre_ai_locked_at?: string | null
  ai_revealed_at?: string | null
  final_locked_at?: string | null
  adjudicated_at?: string | null
  pre_ai_decision?: ResearchDecisionRecord | null
  ai_reveal?: ResearchAIReveal | null
  final_decision?: ResearchFinalDecision | null
  follow_up: ResearchFollowUpPlan
}

export interface ResearchEpisodeList {
  total: number
  items: ResearchEpisode[]
}

export interface ResearchDecisionSubmission {
  task_schema_version: string
  decision: Record<string, any>
  confidence: number
  client_active_seconds?: number | null
  client_started_at?: string | null
  client_submitted_at?: string | null
}

export interface ResearchFinalSubmission extends ResearchDecisionSubmission {
  agreement?: 'agree' | 'partial' | 'disagree' | null
  override?: boolean | null
  override_reason?: string | null
  usefulness?: number | null
}

export interface ResearchEventSubmission {
  event_uuid: string
  idempotency_key: string
  sequence_no: number
  event_type: string
  schema_version: string
  client_timestamp: string
  client_timezone_offset_minutes: number
  payload?: Record<string, any> | null
}

export interface ResearchEventResult {
  id: number
  event_uuid: string
  sequence_no: number
  event_type: string
  server_timestamp: string
  duplicate: boolean
}

export interface StudyInstrument {
  id: number
  study_code: string
  code: string
  version: string
  name: string
  construct: string
  definition: {
    instructions?: string
    questions?: Array<{
      id: string
      label: string
      type: 'likert' | 'number' | 'text' | 'select'
      required?: boolean
      min?: number
      max?: number
      options?: string[]
    }>
  }
  schedule?: Record<string, any> | null
  is_active: boolean
}

export interface ReferenceQueueItem {
  episode_id: number
  case_code: string
  site_code: string
  epoch_code: string
  state: ResearchEpisodeState
  image_count: number
  submitted_review_rounds: number[]
  total_reference_reviews: number
  required_reference_reviews: number
  adjudication_ready: boolean
}

export interface ReferenceCase {
  episode_id: number
  case_code: string
  site_code: string
  epoch_code: string
  state: ResearchEpisodeState
  images: Array<{
    id: number
    filename: string
    content_type?: string | null
    image_url: string
  }>
}

export interface ReferenceAssessment {
  id: number
  episode_id: number
  reviewer_participant_code: string
  review_round: number
  task_schema_version: string
  decision?: Record<string, any>
  confidence?: number | null
  blinded_to_clinician: boolean
  submitted_at: string
  content_sha256: string
}

export interface ResearchEligibleUser {
  id: number
  email: string
  full_name?: string | null
  is_enrolled: boolean
  participant_code?: string | null
  role?: ResearchRole | null
}

export const researchAPI = {
  async context(studyCode = 'ORTHOAI-HCI-V3'): Promise<ResearchContext> {
    const response = await apiFetch(
      `/api/v1/research/context?study_code=${encodeURIComponent(studyCode)}`,
      { method: 'GET' },
    )
    return response.json()
  },

  async ensureClinicianAccess(
    studyCode = 'ORTHOAI-HCI-V3',
  ): Promise<ResearchContext> {
    const response = await apiFetch('/api/v1/research/participants/ensure-clinician', {
      method: 'POST',
      body: JSON.stringify({ study_code: studyCode }),
    })
    return response.json()
  },

  async createEpisode(
    studyCode: string,
    caseId: number,
    clientSessionId: string,
    conditionCode?: string,
  ): Promise<ResearchEpisode> {
    const response = await apiFetch('/api/v1/research/episodes', {
      method: 'POST',
      body: JSON.stringify({
        study_code: studyCode,
        case_id: caseId,
        client_session_id: clientSessionId,
        condition_code: conditionCode || null,
      }),
    })
    return response.json()
  },

  async nextEpisode(
    studyCode: string,
    clientSessionId: string,
    conditionCode?: string,
  ): Promise<ResearchEpisode> {
    const response = await apiFetch('/api/v1/research/episodes/next', {
      method: 'POST',
      body: JSON.stringify({
        study_code: studyCode,
        client_session_id: clientSessionId,
        condition_code: conditionCode || null,
      }),
    })
    return response.json()
  },

  async repeatEpisode(
    episodeId: number,
    clientSessionId: string,
    reasonCode:
      | 'participant_requested'
      | 'new_clinical_opinion'
      | 'workflow_practice'
      | 'other' = 'participant_requested',
  ): Promise<ResearchEpisode> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/repeat`,
      {
        method: 'POST',
        body: JSON.stringify({
          client_session_id: clientSessionId,
          reason_code: reasonCode,
        }),
      },
    )
    return response.json()
  },

  async listEpisodes(studyCode: string): Promise<ResearchEpisodeList> {
    const response = await apiFetch(
      `/api/v1/research/episodes?study_code=${encodeURIComponent(studyCode)}`,
      { method: 'GET' },
    )
    return response.json()
  },

  async getEpisode(episodeId: number): Promise<ResearchEpisode> {
    const response = await apiFetch(`/api/v1/research/episodes/${episodeId}`, {
      method: 'GET',
    })
    return response.json()
  },

  async sourceCase(episodeId: number): Promise<ReferenceCase> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/source-case`,
      { method: 'GET' },
    )
    return response.json()
  },

  async sourceImage(episodeId: number, imageId: number): Promise<Blob> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/source-images/${imageId}`,
      { method: 'GET' },
    )
    return response.blob()
  },

  async appendEvent(
    episodeId: number,
    event: ResearchEventSubmission,
  ): Promise<ResearchEventResult> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/events`,
      {
        method: 'POST',
        body: JSON.stringify(event),
      },
    )
    return response.json()
  },

  async lockPreAI(
    episodeId: number,
    payload: ResearchDecisionSubmission,
  ): Promise<ResearchEpisode> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/pre-ai`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    )
    return response.json()
  },

  async revealAI(episodeId: number): Promise<ResearchEpisode> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/reveal`,
      { method: 'POST' },
    )
    return response.json()
  },

  async lockFinal(
    episodeId: number,
    payload: ResearchFinalSubmission,
  ): Promise<ResearchEpisode> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/final`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    )
    return response.json()
  },

  async instruments(studyCode: string): Promise<StudyInstrument[]> {
    const response = await apiFetch(
      `/api/v1/research/instruments?study_code=${encodeURIComponent(studyCode)}`,
      { method: 'GET' },
    )
    return response.json()
  },

  async submitSurvey(payload: {
    study_code: string
    instrument_code: string
    instrument_version: string
    episode_id?: number | null
    period_code: string
    responses?: Record<string, any> | null
    completion_status: 'completed' | 'declined' | 'missed'
    missing_reason?: string | null
    client_started_at?: string | null
    client_submitted_at?: string | null
  }): Promise<Record<string, any>> {
    const response = await apiFetch('/api/v1/research/surveys', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    return response.json()
  },

  async referenceQueue(studyCode: string): Promise<ReferenceQueueItem[]> {
    const response = await apiFetch(
      `/api/v1/research/reference-queue?study_code=${encodeURIComponent(studyCode)}`,
      { method: 'GET' },
    )
    return response.json()
  },

  async referenceCase(episodeId: number): Promise<ReferenceCase> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/reference-case`,
      { method: 'GET' },
    )
    return response.json()
  },

  async referenceImage(episodeId: number, imageId: number): Promise<Blob> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/reference-images/${imageId}`,
      { method: 'GET' },
    )
    return response.blob()
  },

  async submitReferenceAssessment(
    episodeId: number,
    payload: {
      task_schema_version: string
      decision: Record<string, any>
      confidence?: number | null
      review_round?: number
      blinded_to_clinician: true
    },
  ): Promise<ReferenceAssessment> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/reference-assessments`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    )
    return response.json()
  },

  async referenceAssessments(
    episodeId: number,
  ): Promise<ReferenceAssessment[]> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/reference-assessments`,
      { method: 'GET' },
    )
    return response.json()
  },

  async submitAdjudication(
    episodeId: number,
    payload: {
      reference_standard_version: string
      task_schema_version: string
      consensus_decision: Record<string, any>
      uncertainty?: string | null
      rationale?: string | null
    },
  ): Promise<Record<string, any>> {
    const response = await apiFetch(
      `/api/v1/research/episodes/${episodeId}/adjudication`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    )
    return response.json()
  },

  async participants(studyCode: string): Promise<ResearchParticipant[]> {
    const response = await apiFetch(
      `/api/v1/research/participants?study_code=${encodeURIComponent(studyCode)}`,
      { method: 'GET' },
    )
    return response.json()
  },

  async eligibleUsers(studyCode: string): Promise<ResearchEligibleUser[]> {
    const response = await apiFetch(
      `/api/v1/research/eligible-users?study_code=${encodeURIComponent(studyCode)}`,
      { method: 'GET' },
    )
    return response.json()
  },

  async createParticipant(payload: {
    study_code: string
    site_code: string
    user_id: number
    participant_code: string
    role: ResearchRole
    specialty?: string | null
    experience_band?: string | null
    consent_version: string
    consented_at: string
  }): Promise<ResearchParticipant> {
    const response = await apiFetch('/api/v1/research/participants', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    return response.json()
  },

  async exportStudy(studyCode: string): Promise<Record<string, any>> {
    const response = await apiFetch(
      `/api/v1/research/studies/${encodeURIComponent(studyCode)}/export`,
      { method: 'GET' },
    )
    return response.json()
  },
}

// ===================== Browser-only UX preview =====================

type DemoState = {
  email: string
  termsAccepted: boolean
  nextCaseId: number
  nextImageId: number
  nextJobId: number
  nextEpisodeId: number
  cases: Array<CaseResponse & { images: Array<{ id: number; filename: string }> }>
  jobs: Array<{
    id: number
    case_id: number
    state: JobState
    progress: number
    polls: number
    created_at: string
    started_at?: string | null
    completed_at?: string | null
  }>
  episodes: ResearchEpisode[]
}

const DEMO_STATE_KEY = 'orthoaiUiOnlyDemoStateV1'
const DEMO_OTP = '246810'

function initialDemoState(): DemoState {
  return {
    email: 'clinician@example.com',
    termsAccepted: false,
    nextCaseId: 1,
    nextImageId: 1,
    nextJobId: 1,
    nextEpisodeId: 1,
    cases: [],
    jobs: [],
    episodes: [],
  }
}

function readDemoState(): DemoState {
  if (typeof window === 'undefined') return initialDemoState()
  const stored = sessionStorage.getItem(DEMO_STATE_KEY)
  if (!stored) return initialDemoState()
  try {
    return JSON.parse(stored) as DemoState
  } catch {
    return initialDemoState()
  }
}

function writeDemoState(state: DemoState): void {
  if (typeof window !== 'undefined') {
    sessionStorage.setItem(DEMO_STATE_KEY, JSON.stringify(state))
  }
}

function parseDemoBody(options: RequestInit): Record<string, any> {
  if (typeof options.body !== 'string' || !options.body) return {}
  try {
    return JSON.parse(options.body)
  } catch {
    return {}
  }
}

function demoJson(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function demoParticipant(): ResearchParticipant {
  return {
    id: 1,
    study_code: 'ORTHOAI-HCI-V3',
    site_code: 'LOCAL-UX',
    participant_code: 'UX-PREVIEW',
    role: 'clinician',
    specialty: 'Orthodontics',
    experience_band: 'Preview',
    consent_version: 'v3-preview',
    consented_at: new Date().toISOString(),
    is_active: true,
  }
}

function demoContext(): ResearchContext {
  return {
    enabled: true,
    participant: demoParticipant(),
    study_status: 'active',
    protocol_version: 'v3-ui-preview',
    consent_version: 'v3-preview',
    active_epoch_code: 'UX-PREVIEW',
    ui_version: 'research-mode-v3',
  }
}

function demoFollowUp(): ResearchFollowUpPlan {
  return {
    required: false,
    kind: 'none',
    triggers: [],
    instrument_code: 'ai-influence-micro',
    instrument_version: '1.0.0',
    completed: true,
  }
}

function makeDemoResults(caseId: number): CaseResultsResponse {
  const state = readDemoState()
  const caseItem = state.cases.find((item) => item.id === caseId)
  const images = caseItem?.images.length
    ? caseItem.images
    : [{ id: 1, filename: 'panoramic-preview.jpg' }]
  const prediction = {
    predicted_class: 'Class II div 1',
    confidence: 0.91,
  }
  const quantitativeSummary = {
    total_instances: 14,
    classes_present: 3,
    classes: [
      {
        label: 'Permanent Teeth',
        instance_count: 11,
        image_count: images.length,
        mean_confidence: 0.94,
        mean_instance_area_percent: 4.72,
      },
      {
        label: 'Filling',
        instance_count: 2,
        image_count: 1,
        mean_confidence: 0.88,
        mean_instance_area_percent: 0.82,
      },
      {
        label: 'Caries',
        instance_count: 1,
        image_count: 1,
        mean_confidence: 0.79,
        mean_instance_area_percent: 0.34,
      },
    ],
  }
  const perImage = images.map((image, index) => ({
    image_id: image.id,
    filename: image.filename,
    confidence: index === 0 ? 0.91 : 0.86,
    findings: {
      width_pixels: 1600,
      height_pixels: 900,
      detections: [
        { label: 'Permanent Teeth', confidence: 0.94 },
        { label: 'Filling', confidence: 0.88 },
        ...(index === 0 ? [{ label: 'Caries', confidence: 0.79 }] : []),
      ],
    },
  }))
  return {
    case_id: caseId,
    model_version: 'OrthoAI v3 · UX preview',
    findings: {
      prediction,
      quantitative_summary: quantitativeSummary,
      models: {
        malocclusion: { prediction },
        dental_segmentation: { quantitative_summary: quantitativeSummary },
      },
    },
    summary:
      'Preview finding: Class II division 1 pattern with dental segmentation evidence. This sample is for interface review only.',
    confidences: { malocclusion: 0.91, dental_segmentation: 0.87 },
    per_image_evidence: perImage,
    created_at: new Date().toISOString(),
  }
}

function makeDemoEpisode(
  state: DemoState,
  caseId: number,
  attemptIndex = 1,
  repeatOfEpisodeId: number | null = null,
): ResearchEpisode {
  const now = new Date().toISOString()
  const episode: ResearchEpisode = {
    id: state.nextEpisodeId++,
    study_code: 'ORTHOAI-HCI-V3',
    site_code: 'LOCAL-UX',
    epoch_code: 'UX-PREVIEW',
    participant_code: 'UX-PREVIEW',
    case_id: caseId,
    state: 'pre_ai',
    condition_code: repeatOfEpisodeId ? 'participant_repeat' : 'standard',
    exposure_index: state.episodes.length + 1,
    attempt_index: attemptIndex,
    repeat_of_episode_id: repeatOfEpisodeId,
    last_event_sequence: 0,
    pre_ai_started_at: now,
    follow_up: demoFollowUp(),
  }
  state.episodes.unshift(episode)
  writeDemoState(state)
  return episode
}

async function demoUploadImages(
  caseId: number,
  files: UploadImage[],
): Promise<ImageUploadResponse> {
  const state = readDemoState()
  const caseItem = state.cases.find((item) => item.id === caseId)
  if (!caseItem) throw new Error('Preview case not found.')
  const imageIds = files.map(({ file }) => {
    const id = state.nextImageId++
    caseItem.images.push({ id, filename: file.name || `clinical-image-${id}.jpg` })
    return id
  })
  writeDemoState(state)
  return { image_ids: imageIds }
}

function escapeDemoText(value: string): string {
  return value.replace(/[&<>"']/g, (character) => {
    const entities: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&apos;',
    }
    return entities[character]
  })
}

function demoImageBlob(caseId: number, imageId: number): Blob {
  const state = readDemoState()
  const caseItem = state.cases.find((item) => item.id === caseId)
  const filename =
    caseItem?.images.find((image) => image.id === imageId)?.filename ||
    `Clinical image ${imageId}`
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">
    <defs><linearGradient id="g" x1="0" x2="1"><stop stop-color="#101827"/><stop offset="1" stop-color="#334155"/></linearGradient></defs>
    <rect width="1600" height="900" fill="url(#g)"/>
    <ellipse cx="800" cy="450" rx="570" ry="280" fill="none" stroke="#dbeafe" stroke-width="34" opacity=".72"/>
    <path d="M310 455 Q800 775 1290 455" fill="none" stroke="#f8fafc" stroke-width="62" opacity=".8"/>
    <path d="M345 408 Q800 125 1255 408" fill="none" stroke="#e2e8f0" stroke-width="58" opacity=".76"/>
    <text x="800" y="820" text-anchor="middle" fill="#cbd5e1" font-family="Arial" font-size="30">${escapeDemoText(filename)} · local UX preview</text>
  </svg>`
  return new Blob([svg], { type: 'image/svg+xml' })
}

async function demoApiFetch(
  endpoint: string,
  options: RequestInit,
): Promise<Response> {
  const url = new URL(endpoint, 'http://local-preview.invalid')
  const path = url.pathname
  const method = String(options.method || 'GET').toUpperCase()
  const body = parseDemoBody(options)
  const state = readDemoState()
  const now = new Date().toISOString()

  if (path === '/api/v1/auth/request-otp' && method === 'POST') {
    state.email = String(body.email || state.email)
    writeDemoState(state)
    return demoJson({ message: 'Preview code ready', dev_otp: DEMO_OTP })
  }
  if (path === '/api/v1/auth/login' && method === 'POST') {
    state.email = String(body.email || state.email)
    writeDemoState(state)
    return demoJson({ access_token: 'local-ui-preview-token', token_type: 'bearer' })
  }
  if (path === '/api/v1/auth/me') {
    return demoJson({
      id: 1,
      email: state.email,
      auth_provider: 'local-preview',
      full_name: 'UX Preview Clinician',
      is_active: true,
      terms_accepted: Boolean(state.termsAccepted),
      terms_accepted_at: state.termsAccepted ? now : null,
      last_login_at: now,
      created_at: now,
    })
  }
  if (path === '/api/v1/auth/accept-terms' && method === 'PUT') {
    state.termsAccepted = true
    writeDemoState(state)
    return demoJson({
      message: 'Terms accepted',
      id: 1,
      email: state.email,
      auth_provider: 'local-preview',
      full_name: 'UX Preview Clinician',
      is_active: true,
      terms_accepted: true,
      terms_accepted_at: now,
      last_login_at: now,
      created_at: now,
    })
  }

  if (path === '/api/v1/cases' && method === 'POST') {
    const created: DemoState['cases'][number] = {
      id: state.nextCaseId++,
      user_id: 1,
      consent_checked: Boolean(body.consent_checked),
      patient_id: String(body.patient_id || `PT-${state.nextCaseId - 1}`),
      title: String(body.title || `Case ${state.nextCaseId - 1}`),
      clinic_location: body.clinic_location || 'Local UX preview',
      note: body.note || '',
      tags: Array.isArray(body.tags) ? body.tags : [],
      status: 'queued',
      created_at: now,
      images: [],
    }
    state.cases.unshift(created)
    writeDemoState(state)
    return demoJson(created, 201)
  }
  if (path === '/api/v1/cases' && method === 'GET') {
    return demoJson(state.cases)
  }

  const caseMatch = path.match(/^\/api\/v1\/cases\/(\d+)$/)
  if (caseMatch && method === 'GET') {
    const caseItem = state.cases.find((item) => item.id === Number(caseMatch[1]))
    return caseItem
      ? demoJson(caseItem)
      : demoJson({ detail: 'Preview case not found.' }, 404)
  }
  const noteMatch = path.match(/^\/api\/v1\/cases\/(\d+)\/notes$/)
  if (noteMatch && method === 'POST') {
    return demoJson({
      id: Date.now(),
      case_id: Number(noteMatch[1]),
      content: String(body.content || ''),
      created_by: 1,
      created_at: now,
    }, 201)
  }

  if (path === '/api/v1/inference' && method === 'POST') {
    const caseId = Number(body.case_id)
    const caseItem = state.cases.find((item) => item.id === caseId)
    if (!caseItem) return demoJson({ detail: 'Preview case not found.' }, 404)
    caseItem.status = 'running'
    const job = {
      id: state.nextJobId++,
      case_id: caseId,
      state: 'queued' as JobState,
      progress: 0,
      polls: 0,
      created_at: now,
      started_at: null,
      completed_at: null,
    }
    state.jobs.push(job)
    writeDemoState(state)
    return demoJson({ job_id: job.id }, 201)
  }
  const statusMatch = path.match(/^\/api\/v1\/inference\/(\d+)\/status$/)
  if (statusMatch) {
    const job = state.jobs.find((item) => item.id === Number(statusMatch[1]))
    if (!job) return demoJson({ detail: 'Preview job not found.' }, 404)
    job.polls += 1
    if (job.polls >= 2) {
      job.state = 'done'
      job.progress = 1
      job.started_at ||= now
      job.completed_at = now
      const caseItem = state.cases.find((item) => item.id === job.case_id)
      if (caseItem) caseItem.status = 'done'
    } else {
      job.state = 'running'
      job.progress = 0.58
      job.started_at ||= now
    }
    writeDemoState(state)
    return demoJson(job)
  }
  const cancelMatch = path.match(/^\/api\/v1\/inference\/(\d+)\/cancel$/)
  if (cancelMatch && method === 'POST') {
    const job = state.jobs.find((item) => item.id === Number(cancelMatch[1]))
    if (job) job.state = 'error'
    writeDemoState(state)
    return new Response(null, { status: 204 })
  }

  const resultMatch = path.match(/^\/api\/v1\/cases\/(\d+)\/results$/)
  if (resultMatch) return demoJson(makeDemoResults(Number(resultMatch[1])))
  const explanationMatch = path.match(/^\/api\/v1\/cases\/(\d+)\/explanation$/)
  if (explanationMatch) {
    return demoJson({
      case_id: Number(explanationMatch[1]),
      explanation:
        'This local sample demonstrates the structured explanation layout. It is not a clinical interpretation and no patient data has left the browser.',
      source: 'fallback',
      model_version: 'UX preview',
    })
  }

  if (path === '/api/v1/research/context') return demoJson(demoContext())
  if (
    path === '/api/v1/research/participants/ensure-clinician' &&
    method === 'POST'
  ) {
    return demoJson(demoContext())
  }
  if (path === '/api/v1/research/instruments') return demoJson([])
  if (path === '/api/v1/research/surveys' && method === 'POST') {
    return demoJson({ id: Date.now(), completion_status: body.completion_status }, 201)
  }
  if (path === '/api/v1/research/episodes' && method === 'GET') {
    return demoJson({ total: state.episodes.length, items: state.episodes })
  }
  if (path === '/api/v1/research/episodes' && method === 'POST') {
    const existing = state.episodes.find((item) => item.case_id === Number(body.case_id))
    return demoJson(existing || makeDemoEpisode(state, Number(body.case_id)), 201)
  }
  if (path === '/api/v1/research/episodes/next' && method === 'POST') {
    const nextCase = state.cases.find(
      (item) => !state.episodes.some((episode) => episode.case_id === item.id),
    )
    return nextCase
      ? demoJson(makeDemoEpisode(state, nextCase.id), 201)
      : demoJson({ detail: 'No preview case is waiting.' }, 404)
  }

  const repeatMatch = path.match(/^\/api\/v1\/research\/episodes\/(\d+)\/repeat$/)
  if (repeatMatch && method === 'POST') {
    const source = state.episodes.find((item) => item.id === Number(repeatMatch[1]))
    if (!source) return demoJson({ detail: 'Preview episode not found.' }, 404)
    const attempt = Math.max(
      0,
      ...state.episodes
        .filter((item) => item.case_id === source.case_id)
        .map((item) => item.attempt_index),
    ) + 1
    return demoJson(makeDemoEpisode(state, source.case_id, attempt, source.id), 201)
  }

  const sourceCaseMatch = path.match(
    /^\/api\/v1\/research\/episodes\/(\d+)\/source-case$/,
  )
  if (sourceCaseMatch) {
    const episode = state.episodes.find((item) => item.id === Number(sourceCaseMatch[1]))
    const caseItem = state.cases.find((item) => item.id === episode?.case_id)
    if (!episode || !caseItem) {
      return demoJson({ detail: 'Preview episode not found.' }, 404)
    }
    const images = caseItem.images.length
      ? caseItem.images
      : [{ id: 1, filename: 'panoramic-preview.jpg' }]
    return demoJson({
      episode_id: episode.id,
      case_code: `CASE-${caseItem.id}`,
      site_code: episode.site_code,
      epoch_code: episode.epoch_code,
      state: episode.state,
      images: images.map((image) => ({
        id: image.id,
        filename: image.filename,
        content_type: 'image/svg+xml',
        image_url: '',
      })),
    })
  }
  const sourceImageMatch = path.match(
    /^\/api\/v1\/research\/episodes\/(\d+)\/source-images\/(\d+)$/,
  )
  if (sourceImageMatch) {
    const episode = state.episodes.find((item) => item.id === Number(sourceImageMatch[1]))
    return episode
      ? new Response(demoImageBlob(episode.case_id, Number(sourceImageMatch[2])), {
          status: 200,
          headers: { 'Content-Type': 'image/svg+xml' },
        })
      : demoJson({ detail: 'Preview episode not found.' }, 404)
  }
  const eventMatch = path.match(
    /^\/api\/v1\/research\/episodes\/(\d+)\/events$/,
  )
  if (eventMatch && method === 'POST') {
    const episode = state.episodes.find((item) => item.id === Number(eventMatch[1]))
    if (!episode) return demoJson({ detail: 'Preview episode not found.' }, 404)
    episode.last_event_sequence = Math.max(
      episode.last_event_sequence + 1,
      Number(body.sequence_no || 0),
    )
    writeDemoState(state)
    return demoJson({
      id: Date.now(),
      event_uuid: body.event_uuid,
      sequence_no: episode.last_event_sequence,
      event_type: body.event_type,
      server_timestamp: now,
      duplicate: false,
    }, 201)
  }
  const preAiMatch = path.match(
    /^\/api\/v1\/research\/episodes\/(\d+)\/pre-ai$/,
  )
  if (preAiMatch && method === 'POST') {
    const episode = state.episodes.find((item) => item.id === Number(preAiMatch[1]))
    if (!episode) return demoJson({ detail: 'Preview episode not found.' }, 404)
    episode.state = 'pre_ai_locked'
    episode.pre_ai_locked_at = now
    episode.pre_ai_decision = {
      id: Date.now(),
      task_schema_version: String(body.task_schema_version || 'preview'),
      decision: body.decision || {},
      confidence: Number(body.confidence || 50),
      client_active_seconds: Number(body.client_active_seconds || 0),
      server_elapsed_seconds: Number(body.client_active_seconds || 0),
      submitted_at: now,
      content_sha256: 'local-preview-pre-ai',
    }
    writeDemoState(state)
    return demoJson(episode)
  }
  const revealMatch = path.match(
    /^\/api\/v1\/research\/episodes\/(\d+)\/reveal$/,
  )
  if (revealMatch && method === 'POST') {
    const episode = state.episodes.find((item) => item.id === Number(revealMatch[1]))
    if (!episode) return demoJson({ detail: 'Preview episode not found.' }, 404)
    episode.state = 'ai_revealed'
    episode.ai_revealed_at = now
    episode.ai_reveal = {
      id: Date.now(),
      model_version: 'OrthoAI v3 · UX preview',
      result_schema_version: 'preview/1.0',
      ui_version: 'research-mode-v3',
      payload: makeDemoResults(episode.case_id),
      payload_sha256: 'local-preview-ai-snapshot',
      provenance: { mode: 'browser_only', clinical_use: false },
      inference_created_at: now,
      revealed_at: now,
    }
    writeDemoState(state)
    return demoJson(episode)
  }
  const finalMatch = path.match(
    /^\/api\/v1\/research\/episodes\/(\d+)\/final$/,
  )
  if (finalMatch && method === 'POST') {
    const episode = state.episodes.find((item) => item.id === Number(finalMatch[1]))
    if (!episode) return demoJson({ detail: 'Preview episode not found.' }, 404)
    episode.state = 'final_locked'
    episode.final_locked_at = now
    episode.final_decision = {
      id: Date.now(),
      task_schema_version: String(body.task_schema_version || 'preview'),
      decision: body.decision || {},
      confidence: Number(body.confidence || 50),
      client_active_seconds: Number(body.client_active_seconds || 0),
      server_elapsed_seconds: Number(body.client_active_seconds || 0),
      submitted_at: now,
      content_sha256: 'local-preview-final',
      agreement: body.agreement || 'agree',
      override: Boolean(body.override),
      override_reason: body.override_reason || null,
      usefulness: body.usefulness == null ? 4 : Number(body.usefulness),
    }
    episode.follow_up = demoFollowUp()
    writeDemoState(state)
    return demoJson(episode)
  }
  const episodeMatch = path.match(/^\/api\/v1\/research\/episodes\/(\d+)$/)
  if (episodeMatch && method === 'GET') {
    const episode = state.episodes.find((item) => item.id === Number(episodeMatch[1]))
    return episode
      ? demoJson(episode)
      : demoJson({ detail: 'Preview episode not found.' }, 404)
  }

  if (path === '/api/v1/users/activity') {
    return demoJson({
      user: {
        id: 1,
        email: state.email,
        auth_provider: 'local-preview',
        full_name: 'UX Preview Clinician',
        is_active: true,
        terms_accepted: true,
        created_at: now,
      },
      case_count: state.cases.length,
      completed_diagnoses: state.cases.filter((item) => item.status === 'done').length,
      clinical_validation_count: 0,
      cases: state.cases,
      clinical_validations: [],
      audit_logs: [],
    })
  }

  return demoJson(
    { detail: `This interaction is not included in the browser-only UX preview: ${path}` },
    404,
  )
}
