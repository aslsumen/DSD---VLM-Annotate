/**
 * TypeScript mirror of the FastAPI contract in `backend/app/schemas.py`.
 *
 * Timestamps inside candidates are *source-video-relative seconds* with a
 * half-open interval `[start_seconds, end_seconds)`.
 */

export type VideoStatus = "uploaded" | "ready" | "failed";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";
export type JobKind = "candidate_proposal" | "dataset_export";
export type ClipStatus = "pending" | "ready" | "failed" | "skipped";
export type Verdict = "true_positive" | "false_positive";
export type ReviewState = "unreviewed" | "reviewed";
export type ExportStatus = "queued" | "running" | "ready" | "failed";
export type ExportFormat = "zip";

/** `GET /api/v1/health` (public). */
export interface Health {
  status: "ok";
  app: string;
  version: string;
  environment: string;
  database: string;
  adapter: string;
}

/** `GET /api/v1/adapters`. */
export interface AdapterInfo {
  name: string;
  version: string;
  requires_gpu: boolean;
  available: boolean;
  default: boolean;
}

export interface AdaptersResponse {
  adapters: AdapterInfo[];
  default: string;
}

export interface Project {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectInput {
  name: string;
  description?: string;
}

export interface ProjectStats {
  videos_total: number;
  videos_ready: number;
  candidates_total: number;
  reviewed_total: number;
  true_positive_total: number;
  false_positive_total: number;
  unreviewed_total: number;
  jobs_running: number;
  jobs_failed: number;
  exports_ready: number;
}

export interface ActionDefinition {
  id: number;
  project_id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export interface ActionInput {
  name: string;
  description: string;
}

export interface Video {
  id: number;
  project_id: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  status: VideoStatus;
  error_message: string | null;
  created_at: string;
}

export interface Job {
  id: number;
  kind: JobKind;
  status: JobStatus;
  project_id: number;
  video_id: number | null;
  action_id: number | null;
  export_id: number | null;
  progress: number;
  attempts: number;
  max_attempts: number;
  adapter_name: string | null;
  adapter_version: string | null;
  error_code: string | null;
  error_message: string | null;
  available_at: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobInput {
  action_id: number;
  adapter?: string;
  params?: Record<string, unknown>;
}

export interface Annotation {
  verdict: Verdict;
  corrected_start_seconds: number | null;
  corrected_end_seconds: number | null;
  note: string;
  reviewer: string;
  created_at: string;
  updated_at: string;
}

export interface AnnotationInput {
  verdict: Verdict;
  corrected_start_seconds?: number;
  corrected_end_seconds?: number;
  note?: string;
  reviewer?: string;
}

export interface Candidate {
  id: number;
  job_id: number;
  video_id: number;
  action_id: number | null;
  start_seconds: number;
  end_seconds: number;
  preview_start_seconds: number;
  preview_end_seconds: number;
  rank: number;
  score: number;
  model_notes: string;
  clip_status: ClipStatus;
  clip_error: string | null;
  review_state: ReviewState;
  annotation: Annotation | null;
}

export interface CandidateFilters {
  video_id?: number;
  action_id?: number;
  review_state?: ReviewState;
  verdict?: Verdict;
  limit?: number;
}

export interface DatasetExport {
  id: number;
  project_id: number;
  format: ExportFormat;
  status: ExportStatus;
  include_unreviewed: boolean;
  item_count: number;
  size_bytes: number | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
  has_file: boolean;
}

export interface ExportCreated {
  export: DatasetExport;
  job: Job;
}

export interface ExportInput {
  include_unreviewed?: boolean;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

// --------------------------------------------------------------------------- //
// Accounts (Sprint 3 auth API, `backend/app/api/auth.py`)
// --------------------------------------------------------------------------- //

/** Global roles (Requirements Definition v1.2, §3.1). */
export type UserRole = "administrator" | "dataset_admin" | "annotator";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: User;
}

export interface InvitationCreated {
  id: number;
  email: string;
  role: UserRole;
  expires_at: string;
  /** Returned once: no mail transport exists yet, so the inviter shares the link. */
  token: string;
}
