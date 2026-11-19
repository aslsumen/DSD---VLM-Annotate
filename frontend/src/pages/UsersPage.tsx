/**
 * Users (USR-2, USR-4, USR-5; Design Description v1.2, 5.5).
 *
 * Wired to the Sprint 3 auth API: the user list (Administrators only) and
 * invitations. No mail transport exists yet, so the invitation link is shown once
 * for the inviter to send. Not yet available in the backend: role changes and
 * deactivation (USR-7) and dataset assignment from the user (USR-3), because
 * videos are not linked to the new Dataset entity yet.
 */
import { useState } from "react";

import { Dialog, ErrorNotice, Icon, Loading, Notice, PageHeader } from "../components/ui";
import { api, toApiError, type ApiError } from "../lib/api";
import { formatDate, formatDateTime } from "../lib/format";
import { useApiData } from "../lib/hooks";
import { ROLE_LABEL } from "../lib/search";
import { useSession } from "../lib/session";
import type { InvitationCreated, UserRole } from "../types";

function InviteDialog({ onClose, onInvited }: { onClose: () => void; onInvited: () => void }) {
  const session = useSession();
  // Requirements v1.2: a Dataset Administrator invites Annotators and Dataset
  // Administrators. The current API only lets them invite Annotators.
  const roles: UserRole[] =
    session.role === "administrator" ? ["annotator", "dataset_admin", "administrator"] : ["annotator"];
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("annotator");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [created, setCreated] = useState<InvitationCreated | null>(null);
  const [copied, setCopied] = useState(false);

  const link = created ? `${window.location.origin}${window.location.pathname}#/invite/${created.token}` : "";

  async function send() {
    setBusy(true);
    setError(null);
    try {
      const invitation = await api.createInvitation(email.trim(), role);
      setCreated(invitation);
      onInvited();
    } catch (failure) {
      setError(toApiError(failure));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  if (created) {
    return (
      <Dialog
        title="Invitation created"
        onClose={onClose}
        actions={
          <button type="button" className="btn btn-primary" onClick={onClose}>
            Done
          </button>
        }
      >
        <div className="stack">
          <p>
            Send this link to <strong>{created.email}</strong> ({ROLE_LABEL[created.role]}). It works once and
            expires on {formatDateTime(created.expires_at)} (48 hours).
          </p>
          <div className="copy-box">
            <code className="copy-box__text">{link}</code>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => void copy()}>
              <Icon name="copy" size={14} />
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <Notice tone="warning">
            Invitation emails are not sent yet (email service to be chosen). This link is shown only once.
          </Notice>
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog
      title="Invite user"
      onClose={onClose}
      actions={
        <>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!email.trim() || busy}
            onClick={() => void send()}
          >
            {busy ? "Creating…" : "Create invitation"}
          </button>
        </>
      }
    >
      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          if (email.trim()) void send();
        }}
      >
        <div className="field">
          <label htmlFor="invite-email">Email</label>
          <input
            id="invite-email"
            className="input"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@company.com"
          />
        </div>
        <div className="stack-sm">
          <span className="label">Role</span>
          <div className="chips-row" role="radiogroup" aria-label="Role">
            {roles.map((item) => (
              <button
                key={item}
                type="button"
                role="radio"
                aria-checked={role === item}
                className={role === item ? "pill is-on" : "pill"}
                onClick={() => setRole(item)}
              >
                {ROLE_LABEL[item]}
              </button>
            ))}
          </div>
          <span className="muted small">Roles are global: the same role applies to every dataset.</span>
        </div>
        {error ? <ErrorNotice error={error} title="The invitation was not created" /> : null}
      </form>
    </Dialog>
  );
}

export function UsersPage() {
  const session = useSession();
  const isAdmin = session.role === "administrator";
  const users = useApiData(
    (signal) => (isAdmin ? api.listUsers(signal) : Promise.resolve(null)),
    [isAdmin],
  );
  const [inviting, setInviting] = useState(false);

  return (
    <div className="page page--wide">
      <PageHeader
        kicker="Administration"
        title="Users"
        subtitle={
          isAdmin
            ? users.data
              ? `${users.data.length} ${users.data.length === 1 ? "account" : "accounts"}`
              : "Loading accounts…"
            : "Invite Annotators to work on your datasets."
        }
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setInviting(true)}>
            <Icon name="plus" />
            Invite user
          </button>
        }
      />

      {isAdmin ? (
        <>
          {users.error ? <ErrorNotice error={users.error} onRetry={users.reload} /> : null}
          {users.loading && !users.data ? <Loading /> : null}
          {users.data ? (
            users.data.length > 0 ? (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Role</th>
                      <th>Status</th>
                      <th>Member since</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.data.map((user) => (
                      <tr key={user.id}>
                        <td>
                          <div className="stack-xs">
                            <span className="strong">{user.full_name}</span>
                            <span className="muted small">{user.email}</span>
                          </div>
                        </td>
                        <td>{ROLE_LABEL[user.role]}</td>
                        <td>
                          <span className={user.is_active ? "chip chip--done" : "chip chip--failed"}>
                            {user.is_active ? "Active" : "Deactivated"}
                          </span>
                        </td>
                        <td className="muted">{formatDate(user.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Notice>
                No accounts yet. Create the first administrator with the bootstrap command (see the installation
                manual), then invite people here.
              </Notice>
            )
          ) : null}
        </>
      ) : (
        <Notice>The list of users is visible to Administrators only.</Notice>
      )}

      <p className="muted small">
        Not available yet in the API: changing a role, deactivating an account (USR-7) and assigning datasets to a
        user (USR-3). Dataset access will follow once videos belong to datasets in the backend.
      </p>

      {inviting ? <InviteDialog onClose={() => setInviting(false)} onInvited={() => users.reload()} /> : null}
    </div>
  );
}
