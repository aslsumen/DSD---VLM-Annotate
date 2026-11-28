import type { User } from "../types";
import { api, getStoredToken, toApiError, type ApiError } from "./api";

export const SESSION_ENDED = "Your session ended. Sign in again to continue.";
const SESSION_CHECK_INTERVAL = 30_000;

export type SessionSnapshot =
  | { mode: "loading" | "open" }
  | { mode: "signed-out"; notice?: string }
  | { mode: "unavailable"; error: ApiError }
  | { mode: "signed-in"; user: User; token: string };

export async function resolveAnonymousSession(signal: AbortSignal): Promise<SessionSnapshot> {
  try {
    await api.probeOpenAccess(signal);
    return { mode: "open" };
  } catch (failure) {
    signal.throwIfAborted();
    const error = toApiError(failure);
    return error.status === 401 ? { mode: "signed-out" } : { mode: "unavailable", error };
  }
}

export async function resolveSession(
  signal: AbortSignal, token = getStoredToken(),
): Promise<SessionSnapshot> {
  if (!token) return resolveAnonymousSession(signal);
  try {
    const user = await api.me(token, signal);
    return { mode: "signed-in", user, token };
  } catch (failure) {
    signal.throwIfAborted();
    const error = toApiError(failure);
    return error.status === 401
      ? { mode: "signed-out", notice: SESSION_ENDED }
      : { mode: "unavailable", error };
  }
}

export async function endSession(token: string, signal: AbortSignal, checkAnonymous = true): Promise<SessionSnapshot> {
  try {
    if (token) await api.logout(token, signal);
  } catch (failure) {
    signal.throwIfAborted();
    const error = toApiError(failure);
    if (error.status !== 401 || error.code !== "INVALID_SESSION") {
      return { mode: "signed-out", notice: "Signed out locally. Server sign-out could not be confirmed." };
    }
  }
  if (!checkAnonymous) return { mode: "signed-out" };
  const anonymous = await resolveAnonymousSession(signal);
  return anonymous.mode === "unavailable"
    ? { mode: "signed-out", notice: "Signed out. Anonymous access could not be verified." }
    : anonymous;
}

/** Legacy project routes do not validate session tokens. Check independently of the active page. */
export function monitorSession(
  token: string, onResult: (snapshot: SessionSnapshot) => void,
): () => void {
  const controller = new AbortController();
  const { signal } = controller;
  let timer = setTimeout(() => void check(), SESSION_CHECK_INTERVAL);

  let checking = false;
  async function check() {
    if (checking || signal.aborted) return;
    checking = true;
    clearTimeout(timer);
    const result = await resolveSession(signal, token).catch(() => null);
    checking = false;
    if (signal.aborted || !result) return;
    onResult(result);
    if (result.mode === "signed-out") stop();
    else if (!signal.aborted) {
      timer = setTimeout(() => void check(), SESSION_CHECK_INTERVAL);
    }
  }

  function onVisible() {
    if (document.visibilityState === "visible") void check();
  }
  function stop() {
    clearTimeout(timer);
    controller.abort();
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", onVisible);
      document.removeEventListener("resume", check);
    }
  }
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", onVisible);
    document.addEventListener("resume", check);
  }
  return stop;
}
