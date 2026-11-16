import type { FormEvent } from "react";
import { useState } from "react";

import { EmptyState, ErrorNotice } from "../components/ui";
import { api, toApiError } from "../lib/api";
import type { ApiError } from "../lib/api";
import { formatDate } from "../lib/format";
import type { ActionDefinition } from "../types";

interface ActionsPanelProps {
  projectId: number;
  actions: ActionDefinition[];
  onChanged: () => void;
  onNotify: (text: string, tone: "ok" | "danger") => void;
}

export function ActionsPanel({ projectId, actions, onChanged, onNotify }: ActionsPanelProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [confirmingId, setConfirmingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const trimmedName = name.trim();
    const trimmedDescription = description.trim();
    if (!trimmedName) {
      setError(toApiError(new Error("Give the action a short name.")));
      return;
    }
    if (trimmedDescription.length < 3) {
      setError(toApiError(new Error("Describe the action in at least 3 characters.")));
      return;
    }
    setCreating(true);
    try {
      const created = await api.createAction(projectId, {
        name: trimmedName,
        description: trimmedDescription,
      });
      setName("");
      setDescription("");
      onNotify(`Action "${created.name}" created.`, "ok");
      onChanged();
    } catch (failure) {
      setError(toApiError(failure));
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(action: ActionDefinition) {
    setDeletingId(action.id);
    try {
      await api.deleteAction(action.id);
      setConfirmingId(null);
      onNotify(`Action "${action.name}" deleted.`, "ok");
      onChanged();
    } catch (failure) {
      setError(toApiError(failure));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <section className="card panel" aria-labelledby="actions-heading">
      <div className="panel__head">
        <h2 id="actions-heading">Action definitions</h2>
        <p className="muted">The natural-language query the VLM receives.</p>
      </div>

      {actions.length === 0 ? (
        <EmptyState title="No action defined">
          <p>
            Add the action to search for, for example &ldquo;a person waves at the camera&rdquo;.
            You need one before you can start processing a video.
          </p>
        </EmptyState>
      ) : (
        <ul className="action-list">
          {actions.map((action) => (
            <li key={action.id} className="action-item">
              <div className="action-item__body">
                <h3>{action.name}</h3>
                <p className="action-item__description">&ldquo;{action.description}&rdquo;</p>
                <p className="meta">Created {formatDate(action.created_at)}</p>
              </div>
              {confirmingId === action.id ? (
                <div className="confirm confirm--compact">
                  <p>Delete this action definition?</p>
                  <div className="row">
                    <button
                      type="button"
                      className="btn btn--danger btn--small"
                      disabled={deletingId === action.id}
                      onClick={() => void handleDelete(action)}
                    >
                      {deletingId === action.id ? "Deleting…" : "Delete"}
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost btn--small"
                      onClick={() => setConfirmingId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className="btn btn--ghost btn--small"
                  onClick={() => setConfirmingId(action.id)}
                >
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <form className="form" onSubmit={(event) => void handleCreate(event)}>
        <h3 className="form__title">Add an action</h3>
        <div className="field">
          <label htmlFor="action-name">Name</label>
          <input
            id="action-name"
            name="action-name"
            type="text"
            required
            maxLength={200}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Wave at camera"
          />
          <p className="field__hint">A short label for you; it is not sent to the model.</p>
        </div>
        <div className="field">
          <label htmlFor="action-description">Natural-language action</label>
          <textarea
            id="action-description"
            name="action-description"
            rows={3}
            required
            maxLength={5000}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="a person waves at the camera"
          />
          <p className="field__hint">
            This text is what the VLM receives. Mention the person, the gesture and the viewpoint
            (single fixed camera) to keep proposals precise.
          </p>
        </div>

        {error ? <ErrorNotice error={error} /> : null}

        <button
          type="submit"
          className="btn btn--primary btn--small"
          disabled={creating || !name.trim() || description.trim().length < 3}
        >
          {creating ? "Adding…" : "Add action"}
        </button>
      </form>
    </section>
  );
}
