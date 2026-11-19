/**
 * Who is using the app (USR-1, USR-2, NFR-12).
 *
 * Three modes, decided at start-up:
 *   - "signed-in": a session token is stored and GET /auth/me accepts it.
 *   - "open":      the deployment does not require sign-in (VLM_AUTH_REQUIRED unset,
 *                  development). The API treats anonymous calls as an administrator,
 *                  so the full interface is shown and a "Sign in" link stays available.
 *   - "signed-out": sign-in is required and there is no valid session.
 */
import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import type { User, UserRole } from "../types";
import { api, getStoredToken, storeToken, toApiError } from "./api";
import { canManage } from "./search";

export type SessionMode = "loading" | "signed-in" | "open" | "signed-out";

export interface SessionState {
  mode: SessionMode;
  user: User | null;
  /** Effective role: the user's role, or administrator in open (development) mode. */
  role: UserRole;
  canManage: boolean;
  /** Name stored on review decisions (Annotation.reviewer). */
  reviewerName: string;
  signIn: (email: string, password: string) => Promise<void>;
  acceptInvitation: (token: string, fullName: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Called when the API answers 401 on a session that used to work. */
  sessionExpired: () => void;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<SessionMode>("loading");
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function resolve() {
      if (getStoredToken()) {
        try {
          const me = await api.me(controller.signal);
          setUser(me);
          setMode("signed-in");
          return;
        } catch (error) {
          if (controller.signal.aborted) return;
          const apiError = toApiError(error);
          if (apiError.status !== 401) {
            // API unreachable: keep the token, let pages show the network error.
            setMode("open");
            return;
          }
          storeToken("");
        }
      }
      try {
        await api.probeOpenAccess(controller.signal);
        if (!controller.signal.aborted) setMode("open");
      } catch (error) {
        if (controller.signal.aborted) return;
        setMode(toApiError(error).status === 401 ? "signed-out" : "open");
      }
    }
    void resolve();
    return () => controller.abort();
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const response = await api.login(email, password);
    storeToken(response.access_token);
    setUser(response.user);
    setMode("signed-in");
  }, []);

  const acceptInvitation = useCallback(async (token: string, fullName: string, password: string) => {
    const response = await api.acceptInvitation(token, fullName, password);
    storeToken(response.access_token);
    setUser(response.user);
    setMode("signed-in");
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // The session is dropped locally either way.
    }
    storeToken("");
    setUser(null);
    // Re-probe: an open deployment stays usable without an account.
    try {
      await api.probeOpenAccess();
      setMode("open");
    } catch {
      setMode("signed-out");
    }
  }, []);

  const sessionExpired = useCallback(() => {
    storeToken("");
    setUser(null);
    setMode("signed-out");
  }, []);

  const value = useMemo<SessionState>(() => {
    const role: UserRole = user?.role ?? "administrator";
    return {
      mode,
      user,
      role,
      canManage: canManage(role),
      reviewerName: user ? user.full_name || user.email : "anonymous",
      signIn,
      acceptInvitation,
      signOut,
      sessionExpired,
    };
  }, [mode, user, signIn, acceptInvitation, signOut, sessionExpired]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error("useSession must be used inside <SessionProvider>");
  }
  return value;
}
