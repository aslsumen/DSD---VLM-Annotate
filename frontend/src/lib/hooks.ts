import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiError } from "./api";
import { toApiError } from "./api";

export interface ApiDataState<T> {
  data: T | null;
  error: ApiError | null;
  /** True while a request is in flight (including background polling). */
  loading: boolean;
  reload: () => void;
}

/**
 * Loads data with an `AbortSignal`, exposes explicit loading/error state and a
 * stable `reload` used by polling and by "try again" buttons.
 *
 * A failed background poll keeps the last good data on screen and surfaces the
 * error next to it instead of blanking the page.
 */
export function useApiData<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
): ApiDataState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const depsKey = JSON.stringify(deps);
  const previousDepsKey = useRef(depsKey);

  useEffect(() => {
    const controller = new AbortController();
    if (previousDepsKey.current !== depsKey) {
      previousDepsKey.current = depsKey;
      setData(null);
    }
    setLoading(true);
    setError(null);

    loaderRef.current(controller.signal).then(
      (result) => {
        if (controller.signal.aborted) {
          return;
        }
        setData(result);
        setLoading(false);
      },
      (failure: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(toApiError(failure));
        setLoading(false);
      },
    );

    return () => controller.abort();
  }, [depsKey, version]);

  const reload = useCallback(() => setVersion((current) => current + 1), []);

  return { data, error, loading, reload };
}

function readPreference(key: string, fallback: string): string {
  try {
    return window.localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function writePreference(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage may be unavailable (private mode); the setting simply is not kept.
  }
}

/** String preference persisted in localStorage (used for reviewer name). */
export function useStoredString(
  key: string,
  fallback: string,
): [string, (value: string) => void] {
  const [value, setValue] = useState(() => readPreference(key, fallback));
  const update = useCallback(
    (next: string) => {
      setValue(next);
      writePreference(key, next);
    },
    [key],
  );
  return [value, update];
}

/** Boolean preference persisted in localStorage (used for auto-advance). */
export function useStoredBoolean(
  key: string,
  fallback: boolean,
): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(() => readPreference(key, fallback ? "1" : "0") === "1");
  const update = useCallback(
    (next: boolean) => {
      setValue(next);
      writePreference(key, next ? "1" : "0");
    },
    [key],
  );
  return [value, update];
}
