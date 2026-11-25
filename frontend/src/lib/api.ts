/**
 * Typed client for the VLM Annotate FastAPI service.
 *
 * All requests are relative (`/api/v1/...`): Vite proxies them in development
 * and the FastAPI process serves the built app in production. Errors are always
 * raised as `ApiError` carrying the server's `code`, `message` and `details`.
 */
import type {
  ActionDefinition,
  ActionInput,
  AdaptersResponse,
  Annotation,
  AnnotationInput,
  Candidate,
  DatasetExport,
  ExportCreated,
  ExportInput,
  Health,
  InvitationCreated,
  Job,
  JobInput,
  JobStatus,
  Project,
  ProjectInput,
  ProjectStats,
  User,
  UserRole,
  LoginResponse,
  Video,
} from "../types";
import type { ApiErrorBody } from "../types";

export const API_BASE = "/api/v1";
// Holds the session token returned by POST /auth/login (or a deployment-wide
// VLM_API_TOKEN in older setups). Sent as `Authorization: Bearer <token>`.
export const TOKEN_STORAGE_KEY = "vlm-annotate.api-token";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isUnauthenticated(): boolean {
    return this.status === 401;
  }
}

// --------------------------------------------------------------------------- //
// Bearer token (runtime setting, persisted in localStorage)
// --------------------------------------------------------------------------- //

function localStorageOrNull(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function getStoredToken(): string {
  try {
    return localStorageOrNull()?.getItem(TOKEN_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function storeToken(token: string): void {
  const store = localStorageOrNull();
  if (!store) {
    if (token) throw new Error("Browser storage is unavailable. Enable it to sign in.");
    return;
  }
  const trimmed = token.trim();
  if (trimmed) {
    store.setItem(TOKEN_STORAGE_KEY, trimmed);
  } else {
    store.removeItem(TOKEN_STORAGE_KEY);
  }
}

// --------------------------------------------------------------------------- //
// Fetch plumbing
// --------------------------------------------------------------------------- //

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** Explicit authentication for bootstrap, sign-out and anonymous endpoints. */
  token?: string;
  expectedStatus?: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

// Protected pages share a cancellation scope. Explicit auth calls have their own
// lifetime so logout can revoke the captured token after protected requests stop.
let workspace: { token: string | null; controller: AbortController } | undefined;

export function setWorkspaceSession(token: string | null): AbortSignal {
  workspace?.controller.abort();
  const controller = new AbortController();
  workspace = { token, controller };
  if (token === null) controller.abort();
  return controller.signal;
}

function workspaceRequest(signal?: AbortSignal): { token: string; signal?: AbortSignal } {
  const scope = workspace;
  if (!scope) return { token: getStoredToken(), signal };
  scope.controller.signal.throwIfAborted();
  const token = scope.token ?? "";
  // Storage events are asynchronous. Never send a different tab's token from
  // a view that still belongs to the previous principal.
  assertWorkspaceToken(token);
  return { token, signal: signal ? AbortSignal.any([scope.controller.signal, signal]) : scope.controller.signal };
}

function assertWorkspaceToken(token: string): void {
  if (workspace && token !== getStoredToken()) throw new DOMException("Session changed", "AbortError");
}

let sessionUnauthorized: ((token: string) => void) | undefined;

export function watchSessionUnauthorized(listener: (token: string) => void): () => void {
  sessionUnauthorized = listener;
  return () => {
    if (sessionUnauthorized === listener) sessionUnauthorized = undefined;
  };
}

function reportUnauthorized(status: number, token: string): void {
  if (status === 401 && token && token === getStoredToken()) sessionUnauthorized?.(token);
}

function invalidSessionResponse(): ApiError {
  return new ApiError(200, "INVALID_RESPONSE", "The API returned unexpected authentication data.");
}

function isUser(value: unknown): value is User {
  return isRecord(value) && Number.isInteger(value.id) && typeof value.email === "string"
    && typeof value.full_name === "string" && value.is_active === true && typeof value.created_at === "string"
    && (value.role === "administrator" || value.role === "dataset_admin" || value.role === "annotator");
}

function sessionResponse(value: unknown): LoginResponse {
  if (!isRecord(value) || !isUser(value.user) || typeof value.access_token !== "string"
    || !value.access_token.trim() || value.token_type !== "bearer"
    || typeof value.expires_at !== "string" || !Number.isFinite(Date.parse(value.expires_at))) {
    throw invalidSessionResponse();
  }
  return { user: value.user, access_token: value.access_token, token_type: "bearer", expires_at: value.expires_at };
}

function toErrorBody(payload: unknown): ApiErrorBody | null {
  if (!isRecord(payload) || typeof payload.code !== "string" || typeof payload.message !== "string") {
    return null;
  }
  return {
    code: payload.code,
    message: payload.message,
    details: isRecord(payload.details) ? payload.details : null,
  };
}

function parseJson(text: string): { ok: boolean; value: unknown } {
  if (!text) {
    return { ok: true, value: null };
  }
  try {
    return { ok: true, value: JSON.parse(text) as unknown };
  } catch {
    return { ok: false, value: null };
  }
}

function networkError(): ApiError {
  return new ApiError(
    0,
    "NETWORK_ERROR",
    "Could not reach the API. Is the backend running? Start it with " +
      "`uvicorn app.main:app --port 8000` in backend/ and retry.",
  );
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  const text = await response.text();
  const body = toErrorBody(parseJson(text).value);
  return new ApiError(
    response.status,
    body?.code ?? `HTTP_${response.status}`,
    body?.message ?? `Request failed with status ${response.status}.`,
    body?.details ?? null,
  );
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as unknown as T;
  }
  const text = await response.text();
  const parsed = parseJson(text);
  if (!response.ok) {
    const body = toErrorBody(parsed.value);
    throw new ApiError(
      response.status,
      body?.code ?? `HTTP_${response.status}`,
      body?.message ?? `Request failed with status ${response.status}.`,
      body?.details ?? null,
    );
  }
  if (!parsed.ok) {
    throw new ApiError(
      response.status,
      "INVALID_RESPONSE",
      "The server returned a response that is not valid JSON.",
    );
  }
  return parsed.value as T;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  const auth = options.token === undefined
    ? workspaceRequest(options.signal)
    : { token: options.token, signal: AbortSignal.any([
      ...(options.signal ? [options.signal] : []), AbortSignal.timeout(10_000),
    ]) };
  const { token, signal } = auth;
  function checkAborted() {
    if (signal?.aborted && signal.reason?.name === "TimeoutError") {
      throw new ApiError(0, "TIMEOUT", "The API did not respond in time.");
    }
    signal?.throwIfAborted();
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let body: string | undefined;
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method ?? "GET",
      headers,
      body,
      signal,
      cache: options.token === undefined ? undefined : "no-store",
      redirect: options.token === undefined ? undefined : "error",
      credentials: options.token === "" ? "omit" : "same-origin",
    });
  } catch {
    checkAborted();
    throw networkError();
  }
  checkAborted();
  if (options.token !== undefined && response.redirected) throw invalidSessionResponse();
  if (options.token === undefined) reportUnauthorized(response.status, token);
  if (response.ok && options.expectedStatus !== undefined && response.status !== options.expectedStatus) {
    throw new ApiError(response.status, "INVALID_RESPONSE", "The API returned an unexpected status.");
  }
  checkAborted();
  try {
    const result = await parseResponse<T>(response);
    checkAborted();
    if (options.token === undefined) assertWorkspaceToken(token);
    return result;
  } catch (failure) {
    checkAborted();
    throw failure;
  }
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const serialised = search.toString();
  return serialised ? `?${serialised}` : "";
}

// --------------------------------------------------------------------------- //
// Media URLs used directly by <video> / <a> elements
// --------------------------------------------------------------------------- //

export function videoStreamUrl(videoId: number): string {
  return `${API_BASE}/videos/${videoId}/stream`;
}

export function candidateClipUrl(candidateId: number): string {
  return `${API_BASE}/candidates/${candidateId}/clip`;
}

export function exportDownloadUrl(exportId: number): string {
  return `${API_BASE}/exports/${exportId}/download`;
}

// --------------------------------------------------------------------------- //
// Endpoints
// --------------------------------------------------------------------------- //

export const api = {
  // System
  getHealth: (signal?: AbortSignal): Promise<Health> =>
    request<Health>("/health", { signal }),

  listAdapters: (signal?: AbortSignal): Promise<AdaptersResponse> =>
    request<AdaptersResponse>("/adapters", { signal }),

  // Projects
  listProjects: (signal?: AbortSignal): Promise<Project[]> =>
    request<Project[]>("/projects", { signal }),

  getProject: (projectId: number, signal?: AbortSignal): Promise<Project> =>
    request<Project>(`/projects/${projectId}`, { signal }),

  createProject: (input: ProjectInput): Promise<Project> =>
    request<Project>("/projects", { method: "POST", body: input }),

  updateProject: (projectId: number, input: ProjectInput): Promise<Project> =>
    request<Project>(`/projects/${projectId}`, { method: "PATCH", body: input }),

  deleteProject: (projectId: number): Promise<void> =>
    request<void>(`/projects/${projectId}`, { method: "DELETE" }),

  getProjectStats: (projectId: number, signal?: AbortSignal): Promise<ProjectStats> =>
    request<ProjectStats>(`/projects/${projectId}/stats`, { signal }),

  // Action definitions
  listActions: (projectId: number, signal?: AbortSignal): Promise<ActionDefinition[]> =>
    request<ActionDefinition[]>(`/projects/${projectId}/actions`, { signal }),

  createAction: (projectId: number, input: ActionInput): Promise<ActionDefinition> =>
    request<ActionDefinition>(`/projects/${projectId}/actions`, {
      method: "POST",
      body: input,
    }),

  deleteAction: (actionId: number): Promise<void> =>
    request<void>(`/actions/${actionId}`, { method: "DELETE" }),

  // Videos
  listVideos: (projectId: number, signal?: AbortSignal): Promise<Video[]> =>
    request<Video[]>(`/projects/${projectId}/videos`, { signal }),

  getVideo: (videoId: number, signal?: AbortSignal): Promise<Video> =>
    request<Video>(`/videos/${videoId}`, { signal }),

  /** Deletes the video, its jobs, candidates, review decisions and clips. */
  deleteVideo: (videoId: number): Promise<void> =>
    request<void>(`/videos/${videoId}`, { method: "DELETE" }),

  uploadVideo: (
    projectId: number,
    file: File,
    onProgress?: (fraction: number) => void,
  ): Promise<Video> => uploadWithProgress(projectId, file, onProgress),

  // Jobs
  listJobs: (
    params: {
      projectId?: number;
      videoId?: number;
      actionId?: number;
      status?: JobStatus;
      limit?: number;
    },
    signal?: AbortSignal,
  ): Promise<Job[]> =>
    request<Job[]>(
      `/jobs${toQuery({
        project_id: params.projectId,
        video_id: params.videoId,
        action_id: params.actionId,
        status: params.status,
        limit: params.limit,
      })}`,
      { signal },
    ),

  /** One candidate job per video for an action (a "search"): all ready videos or the listed ones. */
  createActionJobs: (
    projectId: number,
    actionId: number,
    input: { video_ids?: number[]; adapter?: string },
    idempotencyKey: string,
  ): Promise<Job[]> =>
    request<Job[]>(`/projects/${projectId}/actions/${actionId}/jobs`, {
      method: "POST",
      body: input,
      headers: { "Idempotency-Key": idempotencyKey },
    }),

  getJob: (jobId: number, signal?: AbortSignal): Promise<Job> =>
    request<Job>(`/jobs/${jobId}`, { signal }),

  createJob: (videoId: number, input: JobInput, idempotencyKey: string): Promise<Job> =>
    request<Job>(`/videos/${videoId}/jobs`, {
      method: "POST",
      body: input,
      headers: { "Idempotency-Key": idempotencyKey },
    }),

  retryJob: (jobId: number): Promise<Job> =>
    request<Job>(`/jobs/${jobId}/retry`, { method: "POST" }),

  cancelJob: (jobId: number): Promise<Job> =>
    request<Job>(`/jobs/${jobId}/cancel`, { method: "POST" }),

  jobCandidates: (jobId: number, signal?: AbortSignal): Promise<Candidate[]> =>
    request<Candidate[]>(`/jobs/${jobId}/candidates`, { signal }),

  projectCandidates: (
    projectId: number,
    params: { actionId?: number; videoId?: number; limit?: number },
    signal?: AbortSignal,
  ): Promise<Candidate[]> =>
    request<Candidate[]>(
      `/projects/${projectId}/candidates${toQuery({
        action_id: params.actionId,
        video_id: params.videoId,
        limit: params.limit ?? 1000,
      })}`,
      { signal },
    ),

  // Annotations
  upsertAnnotation: (candidateId: number, input: AnnotationInput): Promise<Candidate> =>
    request<Candidate>(`/candidates/${candidateId}/annotation`, {
      method: "PUT",
      body: input,
    }),

  deleteAnnotation: (candidateId: number): Promise<void> =>
    request<void>(`/candidates/${candidateId}/annotation`, { method: "DELETE" }),

  // Exports
  listExports: (projectId: number, signal?: AbortSignal): Promise<DatasetExport[]> =>
    request<DatasetExport[]>(`/projects/${projectId}/exports`, { signal }),

  createExport: (projectId: number, input: ExportInput): Promise<ExportCreated> =>
    request<ExportCreated>(`/projects/${projectId}/exports`, { method: "POST", body: input }),

  // Accounts (USR-1, USR-5, NFR-12)
  login: async (email: string, password: string, signal?: AbortSignal): Promise<LoginResponse> =>
    sessionResponse(await request<unknown>("/auth/login", {
      method: "POST", body: { email, password }, token: "", signal, expectedStatus: 200,
    })),

  logout: (token: string, signal?: AbortSignal): Promise<void> =>
    request<void>("/auth/logout", { method: "POST", token, signal, expectedStatus: 204 }),

  me: async (token: string, signal?: AbortSignal): Promise<User> => {
    const user = await request<unknown>("/auth/me", { signal, token, expectedStatus: 200 });
    if (!isUser(user)) throw invalidSessionResponse();
    return user;
  },

  acceptInvitation: async (token: string, fullName: string, password: string, signal?: AbortSignal): Promise<LoginResponse> =>
    sessionResponse(await request<unknown>("/auth/accept-invitation", {
      method: "POST",
      body: { token, full_name: fullName, password },
      token: "", signal, expectedStatus: 201,
    })),

  createInvitation: (email: string, role: UserRole): Promise<InvitationCreated> =>
    request<InvitationCreated>("/auth/invitations", { method: "POST", body: { email, role } }),

  listUsers: (signal?: AbortSignal): Promise<User[]> => request<User[]>("/auth/users", { signal }),

  /**
   * Probe used at start-up: succeeds when the deployment does not require a
   * sign-in (development), fails with 401 when it does.
   */
  probeOpenAccess: async (signal?: AbortSignal): Promise<void> => {
    const datasets = await request<unknown>("/datasets", { signal, token: "", expectedStatus: 200 });
    if (!Array.isArray(datasets) || !datasets.every((dataset: unknown) =>
      isRecord(dataset) && Number.isInteger(dataset.id) && typeof dataset.name === "string"
      && typeof dataset.description === "string" && typeof dataset.created_at === "string"
      && typeof dataset.updated_at === "string"
      && (dataset.created_by_id === null || Number.isInteger(dataset.created_by_id)))) {
      throw invalidSessionResponse();
    }
  },
};

/**
 * Uploads with XMLHttpRequest because `fetch` cannot report upload progress.
 * The multipart field name is `file`, as required by the backend.
 */
function uploadWithProgress(
  projectId: number,
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<Video> {
  const { token, signal } = workspaceRequest();
  return new Promise<Video>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/projects/${projectId}/videos`);
    xhr.setRequestHeader("Accept", "application/json");
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }

    xhr.upload.onprogress = (event: ProgressEvent) => {
      if (event.lengthComputable && onProgress && event.total > 0) {
        onProgress(Math.min(1, event.loaded / event.total));
      }
    };

    const abort = () => xhr.abort();
    signal?.addEventListener("abort", abort, { once: true });
    xhr.onloadend = () => signal?.removeEventListener("abort", abort);
    xhr.onload = () => {
      try {
        signal?.throwIfAborted();
        assertWorkspaceToken(token);
      } catch (error) {
        reject(error);
        return;
      }
      reportUnauthorized(xhr.status, token);
      const parsed = parseJson(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) {
        if (!parsed.ok || parsed.value === null) {
          reject(
            new ApiError(
              xhr.status,
              "INVALID_RESPONSE",
              "The upload finished but the server response could not be read.",
            ),
          );
          return;
        }
        resolve(parsed.value as Video);
        return;
      }
      const body = toErrorBody(parsed.value);
      reject(
        new ApiError(
          xhr.status,
          body?.code ?? `HTTP_${xhr.status}`,
          body?.message ?? `Upload failed with status ${xhr.status}.`,
          body?.details ?? null,
        ),
      );
    };

    xhr.onerror = () => reject(networkError());
    xhr.onabort = () => reject(new ApiError(0, "UPLOAD_ABORTED", "The upload was cancelled."));

    const form = new FormData();
    form.append("file", file, file.name);
    try {
      xhr.send(form);
    } catch (error) {
      signal?.removeEventListener("abort", abort);
      reject(error);
    }
  });
}

/** Idempotency key so a double-click cannot enqueue two identical jobs. */
export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `job-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Downloads an export through `fetch` so the bearer token (when configured) is
 * included. The archive is buffered by the browser before the save dialog opens.
 */
export async function downloadExportFile(exportId: number, filename: string): Promise<void> {
  const headers = new Headers();
  const { token, signal } = workspaceRequest();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(exportDownloadUrl(exportId), { headers, signal });
  } catch (error) {
    signal?.throwIfAborted();
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw networkError();
  }
  signal?.throwIfAborted();
  if (!response.ok) {
    reportUnauthorized(response.status, token);
    throw await errorFromResponse(response);
  }
  const blob = await response.blob();
  signal?.throwIfAborted();
  assertWorkspaceToken(token);
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

export function toApiError(value: unknown): ApiError {
  if (value instanceof ApiError) {
    return value;
  }
  if (value instanceof Error) {
    return new ApiError(0, "CLIENT_ERROR", value.message);
  }
  return new ApiError(0, "CLIENT_ERROR", "An unexpected error occurred.");
}

/** Annotates a candidate as reviewed locally, mirroring the server response. */
export function withAnnotation(candidate: Candidate, annotation: Annotation | null): Candidate {
  return {
    ...candidate,
    annotation,
    review_state: annotation ? "reviewed" : "unreviewed",
  };
}
