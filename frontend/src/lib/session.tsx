import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import type { LoginResponse, User, UserRole } from "../types";
import {
  api, getStoredToken, setWorkspaceSession, storeToken, TOKEN_STORAGE_KEY,
  toApiError, watchSessionUnauthorized, type ApiError,
} from "./api";
import { canManage } from "./search";
import { endSession, monitorSession, resolveSession, SESSION_ENDED, type SessionSnapshot } from "./sessionLifecycle";

export interface ReviewDraft {
  startValue: number;
  endValue: number;
  startText: string;
  endText: string;
  note: string;
}

export interface SessionState {
  mode: SessionSnapshot["mode"];
  user: User | null;
  role: UserRole | null;
  canManage: boolean;
  reviewerName: string;
  signIn: (email: string, password: string, signal: AbortSignal) => Promise<void>;
  acceptInvitation: (token: string, fullName: string, password: string, signal: AbortSignal) => Promise<void>;
  signOut: () => Promise<void>;
  error: ApiError | null;
  notice: string;
  retrySession: () => void;
  workspaceKey: number;
  reviewDrafts: Map<string, ReviewDraft>;
}

const SessionContext = createContext<SessionState | null>(null);
const TAB_SIGNED_OUT = "The session ended in another tab. Sign in again to continue.";

export function SessionProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<SessionSnapshot>({ mode: "loading" });
  const [workspaceKey, setWorkspaceKey] = useState(0);
  const workspace = useRef<{ token: string; user?: User } | null>(null);
  const operation = useRef<AbortController | null>(null);
  const logoutLifetime = useRef<AbortController | null>(null);
  const knownToken = useRef("");
  const reviewDrafts = useRef(new Map<string, ReviewDraft>());
  const draftOwner = useRef<number | null>(null);

  const show = useCallback((next: SessionSnapshot) => {
    const current = workspace.current;
    const allowed = next.mode === "signed-in" ? { token: next.token, user: next.user }
      : next.mode === "open" ? { token: "" } : null;
    if (current?.token !== allowed?.token || current?.user?.id !== allowed?.user?.id
        || current?.user?.role !== allowed?.user?.role) {
      setWorkspaceSession(allowed?.token ?? null);
      workspace.current = allowed;
      setWorkspaceKey((key) => key + 1);
    }
    if (allowed && draftOwner.current !== (allowed.user?.id ?? null)) {
      reviewDrafts.current.clear();
      draftOwner.current = allowed.user?.id ?? null;
    }
    setSnapshot(next);
  }, []);

  const begin = useCallback(() => {
    operation.current?.abort();
    const controller = new AbortController();
    operation.current = controller;
    return controller.signal;
  }, []);

  const clearToken = useCallback(() => {
    try {
      storeToken("");
    } catch {
      // Close the workspace even when the browser refuses to update storage.
    }
    knownToken.current = getStoredToken();
  }, []);

  const observe = useCallback((token: string, signal: AbortSignal, result: SessionSnapshot) => {
    if (signal.aborted || getStoredToken() !== token) return;
    if (token && result.mode === "signed-out") clearToken();
    show(result);
  }, [clearToken, show]);

  const watch = useCallback((token: string, signal: AbortSignal) => {
    const stop = monitorSession(token, (result) => observe(token, signal, result));
    signal.addEventListener("abort", stop, { once: true });
  }, [observe]);

  const retrySession = useCallback(() => {
    const signal = begin();
    const token = getStoredToken();
    knownToken.current = token;
    show({ mode: "loading" });
    void resolveSession(signal, token).then((result) => {
      if (signal.aborted || getStoredToken() !== token) return;
      observe(token, signal, result);
      if (token && result.mode !== "signed-out") watch(token, signal);
    }).catch((failure: unknown) => {
      if (!signal.aborted) show({ mode: "unavailable", error: toApiError(failure) });
    });
  }, [begin, observe, show, watch]);

  useEffect(() => {
    setWorkspaceSession(null);
    const lifetime = new AbortController();
    logoutLifetime.current = lifetime;
    const expire = watchSessionUnauthorized((token) => {
      if (workspace.current?.token !== token || getStoredToken() !== token) return;
      begin();
      clearToken();
      show({ mode: "signed-out", notice: SESSION_ENDED });
    });
    const sync = (event: StorageEvent) => {
      if (event.key !== null && event.key !== TOKEN_STORAGE_KEY) return;
      const token = getStoredToken();
      if (token === knownToken.current) return;
      if (token) retrySession();
      else {
        begin();
        knownToken.current = "";
        show({ mode: "signed-out", notice: TAB_SIGNED_OUT });
      }
    };
    window.addEventListener("storage", sync);
    retrySession();
    return () => {
      window.removeEventListener("storage", sync);
      expire();
      operation.current?.abort();
      lifetime.abort();
      logoutLifetime.current = null;
      setWorkspaceSession(null);
      workspace.current = null;
    };
  }, [begin, clearToken, retrySession, show]);

  const authenticate = useCallback(async (
    request: (signal: AbortSignal) => Promise<LoginResponse>, pageSignal: AbortSignal,
  ) => {
    const token = getStoredToken();
    const current = operation.current?.signal;
    const signal = current ? AbortSignal.any([current, pageSignal]) : pageSignal;
    const response = await request(signal);
    signal.throwIfAborted();
    if (getStoredToken() !== token) throw new DOMException("Session changed", "AbortError");
    storeToken(response.access_token);
    const next = begin();
    knownToken.current = response.access_token;
    show({ mode: "signed-in", user: response.user, token: response.access_token });
    watch(response.access_token, next);
  }, [begin, show, watch]);

  const signIn = useCallback((email: string, password: string, signal: AbortSignal) =>
    authenticate((requestSignal) => api.login(email, password, requestSignal), signal), [authenticate]);

  const acceptInvitation = useCallback((token: string, fullName: string, password: string, signal: AbortSignal) =>
    authenticate((requestSignal) => api.acceptInvitation(token, fullName, password, requestSignal), signal), [authenticate]);

  const signOut = useCallback(async () => {
    const token = workspace.current?.token;
    const revocation = logoutLifetime.current;
    if (!token || !revocation) return;
    const signal = begin();
    show({ mode: "signing-out" });
    reviewDrafts.current.clear();
    if (getStoredToken() === token) clearToken();
    try {
      const result = await endSession(token, revocation.signal);
      if (signal.aborted) return;
      const current = getStoredToken();
      if (current && current !== token) retrySession();
      else if (current) show({ mode: "signed-out", notice: "Signed out here. Browser storage could not be cleared." });
      else show(result);
    } catch (failure) {
      if (!signal.aborted) show({ mode: "unavailable", error: toApiError(failure) });
    }
  }, [begin, clearToken, retrySession, show]);

  const value = useMemo<SessionState>(() => {
    const user = snapshot.mode === "signed-in" ? snapshot.user : null;
    const role = user?.role ?? (snapshot.mode === "open" ? "administrator" : null);
    return {
      mode: snapshot.mode, user, role,
      canManage: role !== null && canManage(role),
      reviewerName: user ? user.full_name || user.email : "anonymous",
      signIn, acceptInvitation, signOut, retrySession, workspaceKey,
      reviewDrafts: reviewDrafts.current,
      error: snapshot.mode === "unavailable" ? snapshot.error : null,
      notice: snapshot.mode === "signed-out" ? snapshot.notice ?? "" : "",
    };
  }, [snapshot, signIn, acceptInvitation, signOut, retrySession, workspaceKey]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside <SessionProvider>");
  return value;
}
