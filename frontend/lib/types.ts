export type JobState = "queued" | "running" | "done" | "error";

export type User = {
  id: number;
  email: string;
  auth_provider: string;
  full_name: string | null;
  avatar_url: string | null;
  is_active: boolean;
  terms_accepted: boolean;
  terms_accepted_at: string | null;
  last_login_at: string | null;
  created_at: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
};

export type OTPResponse = {
  message: string;
  dev_otp?: string | null;
};

export type SSOProvider = {
  provider: string;
  enabled: boolean;
  reason: string | null;
};

export type CaseItem = {
  id: number;
  user_id: number;
  consent_checked: boolean;
  patient_id: string;
  title: string;
  clinic_location: string | null;
  note: string | null;
  tags: string[];
  status: JobState | null;
  created_at: string;
};

export type InferenceStatus = {
  case_id: number;
  state: JobState;
  progress: number;
  error_message: string | null;
  is_terminal: boolean;
  can_cancel: boolean;
  queue_seconds: number | null;
  run_seconds: number | null;
  total_seconds: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type InferenceStart = {
  job_id: number;
};

export type CaseResults = {
  case_id: number;
  model_version: string;
  findings: Record<string, unknown>;
  summary: string;
  confidences: Record<string, number>;
  per_image_evidence: Array<{
    image_id: number;
    filename: string;
    findings: Record<string, unknown>;
    confidence: number;
  }>;
  created_at: string;
};

export type ClinicalPayload = {
  site: string;
  case_id: string;
  assess_date?: string | null;
  clinician?: string | null;
  age?: number | null;
  sex?: "Female" | "Male" | "Other" | "Undisclosed" | null;
  rec_opg: boolean;
  rec_photo: boolean;
  rec_other: boolean;
  m_class: string;
  dhc: number;
  ac?: number | null;
  t_manual?: number | null;
  ai_class?: string | null;
  ai_dhc?: number | null;
  ai_ac?: number | null;
  ai_conf?: number | null;
  t_ai?: number | null;
  calib?: "Well-calibrated" | "Over-confident" | "Under-confident" | "N/A" | null;
  agree?: "Agree" | "Partial" | "Disagree" | null;
  override?: "Yes" | "No" | null;
  override_reason?: string | null;
  useful?: number | null;
  comment?: string | null;
};

export type Activity = {
  user: User;
  case_count: number;
  completed_diagnoses: number;
  clinical_validation_count: number;
  cases: Array<{
    id: number;
    patient_id: string | null;
    title: string | null;
    status: JobState | null;
    has_results: boolean;
    created_at: string;
  }>;
  clinical_validations: Array<{
    id: number;
    orthoai_case_id: number;
    site: string;
    case_id: string;
    m_class: string;
    dhc: number;
    ai_class: string | null;
    ai_dhc: number | null;
    class_match: boolean | null;
    created_at: string;
  }>;
  audit_logs: Array<{
    id: number;
    action: string;
    resource_type: string;
    resource_id: number | null;
    details: Record<string, unknown>;
    ip_address: string | null;
    created_at: string;
  }>;
};

export type ClinicalRecord = {
  id: number;
  orthoai_case_id: number;
  site: string;
  case_id: string;
  m_class: string;
  dhc: number;
  ai_class: string | null;
  ai_dhc: number | null;
  ai_ac?: number | null;
  ai_conf?: number | null;
  agree?: string | null;
  override?: string | null;
  class_match: boolean | null;
  useful: number | null;
  high_need?: boolean;
  dhc_delta?: number | null;
  created_at: string;
};

export type ClinicalList = {
  total: number;
  items: ClinicalRecord[];
};

export type ClinicalStats = {
  n: number;
  sites: number;
  high_need: number;
  class_pairs: number;
  class_agreement_pct: number | null;
  dhc_pairs: number;
  dhc_exact_pct: number | null;
  mean_dhc_delta: number | null;
  mean_useful: number | null;
  override_rate_pct: number | null;
  mean_t_manual: number | null;
  mean_t_ai: number | null;
};
