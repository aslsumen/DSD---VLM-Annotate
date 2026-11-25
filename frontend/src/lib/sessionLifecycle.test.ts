import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, downloadExportFile, setWorkspaceSession, getStoredToken, storeToken, watchSessionUnauthorized } from "./api";
import { endSession, monitorSession, resolveSession, SESSION_ENDED } from "./sessionLifecycle";

const user = {
  id: 1,
  email: "person@example.test",
  full_name: "Test Person",
  role: "annotator",
  created_at: "2026-11-23T12:00:00Z",
  is_active: true,
};

const fetchMock = vi.fn<typeof fetch>();
const signal = () => new AbortController().signal;
const reply = (status: number, body: unknown) => Response.json(body, { status });
const authorization = (call: number) => new Headers(fetchMock.mock.calls[call]?.[1]?.headers).get("Authorization");

beforeEach(() => {
  const storage = new Map<string, string>();
  vi.stubGlobal("window", {
    localStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
      removeItem: (key: string) => storage.delete(key),
    },
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("session bootstrap", () => {
  it("opens development only after a valid anonymous HTTP 200", async () => {
    fetchMock.mockResolvedValueOnce(reply(200, []));
    await expect(resolveSession(signal())).resolves.toEqual({ mode: "open" });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/datasets");
    expect(authorization(0)).toBeNull();
    expect(fetchMock.mock.calls[0]?.[1]?.credentials).toBe("omit");
  });

  it("accepts the existing DatasetOut shape for a populated development deployment", async () => {
    fetchMock.mockResolvedValueOnce(reply(200, [{
      id: 1, name: "Development dataset", description: "", created_by_id: null,
      created_at: "2026-11-23T12:00:00Z", updated_at: "2026-11-23T12:00:00Z",
    }]));
    await expect(resolveSession(signal())).resolves.toEqual({ mode: "open" });
  });

  it.each([{ body: null }, { body: {} }, { body: [null] }, { body: [{ id: 1, name: "unexpected summary" }] }])(
    "keeps the app gated when a 200 probe returns %j",
    async ({ body }) => {
      fetchMock.mockResolvedValueOnce(reply(200, body));
      await expect(resolveSession(signal())).resolves.toMatchObject({
        mode: "unavailable", error: { code: "INVALID_RESPONSE" },
      });
    },
  );

  it.each([201, 204])("rejects unexpected successful status %i on the anonymous probe", async (status) => {
    fetchMock.mockResolvedValueOnce(status === 204 ? new Response(null, { status }) : reply(status, []));
    await expect(resolveSession(signal())).resolves.toMatchObject({
      mode: "unavailable", error: { status, code: "INVALID_RESPONSE" },
    });
  });

  it("rejects a redirected anonymous response even if it contains a valid list", async () => {
    const redirected = reply(200, []);
    Object.defineProperty(redirected, "redirected", { value: true });
    fetchMock.mockResolvedValueOnce(redirected);
    await expect(resolveSession(signal())).resolves.toMatchObject({
      mode: "unavailable", error: { code: "INVALID_RESPONSE" },
    });
  });

  it.each([401, 403, 500, 503])("distinguishes HTTP %i without enabling development mode", async (status) => {
    fetchMock.mockResolvedValueOnce(reply(status, {}));
    await expect(resolveSession(signal())).resolves.toMatchObject(
      status === 401 ? { mode: "signed-out" } : { mode: "unavailable", error: { status } },
    );
  });

  it("allows retry after a network error without opening the app before confirmation", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Network unavailable")).mockResolvedValueOnce(reply(200, []));
    await expect(resolveSession(signal())).resolves.toMatchObject({
      mode: "unavailable", error: { status: 0, code: "NETWORK_ERROR" },
    });
    await expect(resolveSession(signal())).resolves.toEqual({ mode: "open" });
  });

  it("restores the backend role with a valid stored session", async () => {
    storeToken("session");
    fetchMock.mockResolvedValueOnce(reply(200, user));
    await expect(resolveSession(signal())).resolves.toEqual({ mode: "signed-in", user, token: "session" });
    expect(authorization(0)).toBe("Bearer session");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([403, 500, 503])("preserves the token and keeps the app gated after me returns %i", async (status) => {
    storeToken("session");
    fetchMock.mockResolvedValueOnce(reply(status, {}));
    await expect(resolveSession(signal())).resolves.toMatchObject({ mode: "unavailable", error: { status } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(getStoredToken()).toBe("session");
  });

  it("preserves the token and keeps the app gated when me is unreachable", async () => {
    storeToken("session");
    fetchMock.mockRejectedValueOnce(new TypeError("Offline"));
    await expect(resolveSession(signal())).resolves.toMatchObject({
      mode: "unavailable", error: { code: "NETWORK_ERROR" },
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(getStoredToken()).toBe("session");
  });

  it("times out a stalled bootstrap without allowing anonymous access", async () => {
    const timeout = new AbortController();
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeout.signal);
    fetchMock.mockImplementationOnce((_path, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener("abort", () => reject(options.signal?.reason), { once: true });
    }));
    storeToken("session");
    const pending = resolveSession(signal());
    timeout.abort(new DOMException("Timed out", "TimeoutError"));
    await expect(pending).resolves.toMatchObject({ mode: "unavailable", error: { code: "TIMEOUT" } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not hydrate an invalid user payload", async () => {
    storeToken("session");
    fetchMock.mockResolvedValueOnce(reply(200, { ...user, role: "unexpected" }));
    await expect(resolveSession(signal())).resolves.toMatchObject({
      mode: "unavailable", error: { code: "INVALID_RESPONSE" },
    });
    expect(getStoredToken()).toBe("session");
  });

  it("requires sign-in after a stored session expires, without probing as an anonymous admin", async () => {
    storeToken("expired-session");
    fetchMock.mockResolvedValueOnce(reply(401, {}));
    await expect(resolveSession(signal())).resolves.toEqual({ mode: "signed-out", notice: SESSION_ENDED });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rejects an aborted anonymous probe even when transport resolves late", async () => {
    const controller = new AbortController();
    let finish!: (response: Response) => void;
    fetchMock.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const pending = resolveSession(controller.signal);
    controller.abort();
    finish(reply(200, []));
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("public account endpoints", () => {
  const session = { user, access_token: "new-session", token_type: "bearer", expires_at: "2026-11-24T00:00:00Z" };

  it("validates successful login and rejects an unexpected session response", async () => {
    storeToken("previous");
    fetchMock.mockResolvedValueOnce(reply(200, session)).mockResolvedValueOnce(reply(200, { user }));
    await expect(api.login(user.email, "synthetic-password")).resolves.toEqual(session);
    expect(authorization(0)).toBeNull();
    await expect(api.login(user.email, "synthetic-password")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("accepts the server-issued invitation session with no existing bearer header", async () => {
    storeToken("previous");
    fetchMock.mockResolvedValueOnce(reply(201, session));
    await expect(api.acceptInvitation("invitation", "Test Person", "synthetic-password")).resolves.toEqual(session);
    expect(authorization(0)).toBeNull();
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({
      token: "invitation", full_name: "Test Person", password: "synthetic-password",
    });
  });
});

describe("session termination", () => {
  it("notifies on a current authenticated 401 but not 403 or sign-in errors", async () => {
    const expire = vi.fn();
    const unsubscribe = watchSessionUnauthorized(expire);
    try {
      storeToken("current");
      fetchMock
        .mockResolvedValueOnce(reply(403, {}))
        .mockResolvedValueOnce(reply(401, { code: "INVALID_CREDENTIALS", message: "Invalid credentials" }))
        .mockResolvedValueOnce(reply(401, {}));
      await expect(api.listProjects()).rejects.toMatchObject({ status: 403 });
      await expect(api.login("person@example.test", "incorrect")).rejects.toMatchObject({ code: "INVALID_CREDENTIALS" });
      expect(authorization(1)).toBeNull();
      expect(expire).not.toHaveBeenCalled();
      await expect(api.listProjects()).rejects.toMatchObject({ status: 401 });
      expect(expire).toHaveBeenCalledExactlyOnceWith("current");
    } finally {
      unsubscribe();
    }
  });

  it("ignores a 401 from a request sent with a superseded token", async () => {
    let finish!: (response: Response) => void;
    fetchMock.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const expire = vi.fn();
    const unsubscribe = watchSessionUnauthorized(expire);
    try {
      storeToken("previous");
      const pending = api.listProjects();
      storeToken("current");
      finish(reply(401, {}));
      await expect(pending).rejects.toMatchObject({ status: 401 });
      expect(expire).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });

  it("handles the authenticated upload and download paths consistently", async () => {
    class UnauthorizedUpload {
      status = 401;
      responseText = "{}";
      upload = {};
      onload?: () => void;
      open() {}
      setRequestHeader() {}
      send() { this.onload?.(); }
    }
    vi.stubGlobal("XMLHttpRequest", UnauthorizedUpload);
    storeToken("current");
    const expire = vi.fn();
    const unsubscribe = watchSessionUnauthorized(expire);
    try {
      fetchMock.mockResolvedValueOnce(reply(401, {}));
      await expect(downloadExportFile(1, "test.zip")).rejects.toMatchObject({ status: 401 });
      await expect(api.uploadVideo(1, new File([], "test.mp4"))).rejects.toMatchObject({ status: 401 });
      expect(expire.mock.calls).toEqual([["current"], ["current"]]);
    } finally {
      unsubscribe();
    }
  });

  it.each([200, 401])("revokes the passed token and rechecks anonymous access (%i)", async (status) => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 })).mockResolvedValueOnce(reply(status, []));
    await expect(endSession("closing", signal())).resolves.toEqual({ mode: status === 200 ? "open" : "signed-out" });
    expect(authorization(0)).toBe("Bearer closing");
    expect(authorization(1)).toBeNull();
  });

  it("distinguishes a revoked session from an unconfirmed 401 on logout", async () => {
    fetchMock.mockResolvedValueOnce(reply(401, {}));
    await expect(endSession("closing", signal())).resolves.toMatchObject({
      mode: "signed-out", notice: expect.stringContaining("Server sign-out could not be confirmed."),
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fetchMock.mockResolvedValueOnce(reply(401, { code: "INVALID_SESSION", message: "Expired" }))
      .mockResolvedValueOnce(reply(200, []));
    await expect(endSession("closing", signal())).resolves.toEqual({ mode: "open" });
  });

  it("stays signed out when the server could not confirm logout", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Offline"));
    await expect(endSession("closing", signal())).resolves.toMatchObject({
      mode: "signed-out", notice: expect.stringContaining("Server sign-out could not be confirmed."),
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rechecks after a transient heartbeat error, reports recovery, and stops on a real 401", async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValueOnce(reply(503, {})).mockResolvedValueOnce(reply(200, user))
      .mockResolvedValueOnce(reply(401, {}));
    const onResult = vi.fn();
    const stop = monitorSession("session", onResult);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(onResult).toHaveBeenNthCalledWith(1, expect.objectContaining({ mode: "unavailable" }));
    await vi.advanceTimersByTimeAsync(30_000);
    expect(onResult).toHaveBeenNthCalledWith(2, { mode: "signed-in", user, token: "session" });
    await vi.advanceTimersByTimeAsync(60_000);
    expect(onResult).toHaveBeenNthCalledWith(3, { mode: "signed-out", notice: SESSION_ENDED });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    stop();
  });

  it("aborts the heartbeat and leaves no timer after session cleanup", async () => {
    vi.useFakeTimers();
    fetchMock.mockReturnValueOnce(new Promise(() => {}));
    const onResult = vi.fn();
    const stop = monitorSession("session", onResult);
    await vi.advanceTimersByTimeAsync(30_000);
    const inFlight = fetchMock.mock.calls[0]?.[1]?.signal;
    expect(inFlight?.aborted).toBe(false);
    stop();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(inFlight?.aborted).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(onResult).not.toHaveBeenCalled();
  });
});

describe("protected workspace requests", () => {
  it("aborts a late mutation and gates new calls after logout", async () => {
    storeToken("old");
    setWorkspaceSession("old");
    let finish!: (response: Response) => void;
    fetchMock.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const pending = api.deleteProject(1);
    const requestSignal = fetchMock.mock.calls[0]?.[1]?.signal;
    setWorkspaceSession(null);
    expect(requestSignal?.aborted).toBe(true);
    finish(new Response(null, { status: 204 }));
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    await expect(api.listProjects()).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not use a replacement token from storage before the route guard updates", async () => {
    storeToken("old");
    setWorkspaceSession("old");
    storeToken("new");
    await expect(api.listProjects()).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("aborts an XMLHttpRequest upload when its workspace closes", async () => {
    const abort = vi.fn();
    class PendingUpload {
      upload = {};
      onabort?: () => void;
      onloadend?: () => void;
      open() {}
      setRequestHeader() {}
      send() {}
      abort() {
        abort();
        this.onabort?.();
        this.onloadend?.();
      }
    }
    vi.stubGlobal("XMLHttpRequest", PendingUpload);
    storeToken("current");
    setWorkspaceSession("current");
    const pending = api.uploadVideo(1, new File([], "test.mp4"));
    setWorkspaceSession(null);
    await expect(pending).rejects.toMatchObject({ code: "UPLOAD_ABORTED" });
    expect(abort).toHaveBeenCalledTimes(1);
  });
});
