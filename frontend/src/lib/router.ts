/**
 * Hand-rolled hash routing. No router library is used.
 *
 * Supported URLs:
 *   #/                              projects list
 *   #/projects/:id                  project workspace
 *   #/projects/:id/review?job=:job  candidate review
 */
import { useEffect, useState } from "react";

export interface ParsedPath {
  pathname: string;
  query: URLSearchParams;
}

export type Route =
  | { name: "projects" }
  | { name: "project"; projectId: number }
  | { name: "review"; projectId: number; jobId: number | null }
  | { name: "notFound"; pathname: string };

/** Splits `#/projects/1/review?job=2` into a normalised path and a query. */
export function parseHash(hash: string): ParsedPath {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  const queryIndex = raw.indexOf("?");
  const pathPart = queryIndex === -1 ? raw : raw.slice(0, queryIndex);
  const queryPart = queryIndex === -1 ? "" : raw.slice(queryIndex + 1);

  let pathname = pathPart.trim();
  if (!pathname.startsWith("/")) {
    pathname = `/${pathname}`;
  }
  if (pathname.length > 1 && pathname.endsWith("/")) {
    pathname = pathname.slice(0, -1);
  }
  return { pathname, query: new URLSearchParams(queryPart) };
}

function toPositiveInt(value: string | null | undefined): number | null {
  if (!value || !/^\d+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

/** Maps a raw `location.hash` to a typed route. */
export function parseRoute(hash: string): Route {
  const { pathname, query } = parseHash(hash);
  const segments = pathname.split("/").filter((segment) => segment.length > 0);

  if (segments.length === 0) {
    return { name: "projects" };
  }
  if (segments[0] === "projects" && segments.length >= 2) {
    const projectId = toPositiveInt(segments[1]);
    if (projectId === null) {
      return { name: "notFound", pathname };
    }
    if (segments.length === 2) {
      return { name: "project", projectId };
    }
    if (segments.length === 3 && segments[2] === "review") {
      const jobId = toPositiveInt(query.get("job"));
      return { name: "review", projectId, jobId };
    }
  }
  return { name: "notFound", pathname };
}

function currentRoute(): Route {
  if (typeof window === "undefined") {
    return { name: "projects" };
  }
  return parseRoute(window.location.hash);
}

/** Subscribes to hash changes and returns the parsed route. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(currentRoute);

  useEffect(() => {
    const onHashChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return route;
}

/** Navigates to an in-app path such as `/projects/1/review?job=2`. */
export function navigate(path: string): void {
  const target = path.startsWith("/") ? path : `/${path}`;
  window.location.hash = target;
}

/** `href` for use in plain anchors. */
export function href(path: string): string {
  return `#${path.startsWith("/") ? path : `/${path}`}`;
}
