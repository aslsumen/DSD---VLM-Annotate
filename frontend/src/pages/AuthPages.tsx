/**
 * Sign in, password reset and invitation acceptance (USR-1, USR-5, USR-6,
 * NFR-11, NFR-14; Design Description v1.2, 5.2).
 */
import type { FormEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

import { Brand } from "../components/Shell";
import { ErrorNotice, Frame, Icon } from "../components/ui";
import { toApiError } from "../lib/api";
import { navigate } from "../lib/router";
import { useSession } from "../lib/session";

function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-screen">
      <div className="auth-card">
        <Brand large />
        <Frame className="auth-frame">{children}</Frame>
      </div>
    </div>
  );
}

function FieldError({ message }: { message: string }) {
  if (!message) return null;
  return (
    <div className="field-error" role="alert">
      <Icon name="info" size={16} />
      {message}
    </div>
  );
}

/** NFR-14: one neutral message, whether or not the email exists. */
function signInMessage(code: string, fallback: string): string {
  switch (code) {
    case "INVALID_CREDENTIALS":
    case "INVALID_EMAIL":
    case "VALIDATION_ERROR":
      return "Email or password is not correct.";
    case "ACCOUNT_LOCKED":
      return "Too many failed attempts. Sign-in is blocked for 15 minutes.";
    case "ACCOUNT_DISABLED":
      return "This account has been deactivated. Contact your administrator.";
    default:
      return fallback;
  }
}

function useAccountRequest() {
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  return request;
}

export function SignInPage() {
  const session = useSession();
  const request = useAccountRequest();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (request.current) return;
    setError("");
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    try {
      await session.signIn(email.trim(), password, controller.signal);
    } catch (failure) {
      if (controller.signal.aborted) return;
      const apiError = toApiError(failure);
      setError(signInMessage(apiError.code, apiError.message));
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <AuthLayout>
      <form className="stack" onSubmit={(event) => void submit(event)}>
        <h2>Sign in</h2>
        {session.notice ? <p className="muted" role="status">{session.notice}</p> : null}
        <div className="field">
          <label htmlFor="signin-email">Email</label>
          <input
            id="signin-email"
            className="input"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@company.com"
          />
        </div>
        <div className="field">
          <label htmlFor="signin-password">Password</label>
          <input
            id="signin-password"
            className="input"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        <FieldError message={error} />
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <a className="btn btn-ghost align-start" href="#/forgot-password">
          Forgot password?
        </a>
        {session.mode === "open" ? (
          <a className="btn btn-ghost align-start" href="#/">
            Continue without an account (development mode)
          </a>
        ) : null}
      </form>
    </AuthLayout>
  );
}

export function SessionUnavailablePage() {
  const { error, retrySession, signOut, hasRetainedToken } = useSession();
  return (
    <AuthLayout>
      <div className="stack">
        <h2>Authentication unavailable</h2>
        {error ? (
          <ErrorNotice
            error={error}
            title={error.status === 403 ? "Access denied" : "Could not verify access"}
            onRetry={retrySession}
          />
        ) : null}
        {hasRetainedToken && (
          <button className="btn btn-secondary align-start" onClick={() => void signOut()}>Sign out</button>
        )}
        <a className="btn btn-ghost align-start" href="#/signin" onClick={() => void signOut("signin")}>
          Go to sign in
        </a>
      </div>
    </AuthLayout>
  );
}

/** USR-6 is a Should requirement: the email service is not chosen yet (TBD). */
export function ForgotPasswordPage() {
  return (
    <AuthLayout>
      <div className="stack">
        <h2>Reset your password</h2>
        <p className="muted">
          Password reset by email is not available yet: the email service is still to be chosen.
          Ask your administrator to send you a new invitation link.
        </p>
        <a className="btn btn-secondary align-start" href="#/signin">
          Back to sign in
        </a>
      </div>
    </AuthLayout>
  );
}

export function AcceptInvitePage({ token }: { token: string }) {
  const session = useSession();
  const request = useAccountRequest();
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [invalid, setInvalid] = useState<"" | "expired" | "used" | "invalid">("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (request.current) return;
    setError("");
    if (password.length < 8) {
      setError("The password must have at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("The two passwords are different.");
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    try {
      await session.acceptInvitation(token, fullName.trim(), password, controller.signal);
      controller.signal.throwIfAborted();
      navigate("/");
    } catch (failure) {
      if (controller.signal.aborted) return;
      const apiError = toApiError(failure);
      if (apiError.code === "INVITATION_EXPIRED") setInvalid("expired");
      else if (apiError.code === "INVITATION_ALREADY_USED") setInvalid("used");
      else if (apiError.code === "INVITATION_INVALID") setInvalid("invalid");
      else setError(apiError.message);
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  if (invalid) {
    const title =
      invalid === "expired"
        ? "This invitation has expired"
        : invalid === "used"
          ? "This invitation was already used"
          : "This invitation link is not valid";
    return (
      <AuthLayout>
        <div className="stack">
          <Icon name="clock" size={28} className="accent" />
          <h2>{title}</h2>
          <p className="muted">
            Invitation links can be used once and are valid for 48 hours. Ask your administrator to
            send you a new one.
          </p>
          <a className="btn btn-secondary align-start" href="#/signin">
            Go to sign in
          </a>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <form className="stack" onSubmit={(event) => void submit(event)}>
        <div className="kicker">Invitation</div>
        <h2>Create your account</h2>
        <p className="muted">
          You were invited to VLM Annotate. Your role and email were set by the person who invited
          you; sign in later with that email.
        </p>
        <div className="field">
          <label htmlFor="invite-name">Full name</label>
          <input
            id="invite-name"
            className="input"
            required
            autoComplete="name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="invite-password">New password</label>
          <input
            id="invite-password"
            className="input"
            type="password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="invite-confirm">Confirm password</label>
          <input
            id="invite-confirm"
            className="input"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
        </div>
        <div className="muted small">At least 8 characters.</div>
        <FieldError message={error} />
        <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={busy}>
          {busy ? "Creating account…" : "Set password and continue"}
        </button>
      </form>
    </AuthLayout>
  );
}
