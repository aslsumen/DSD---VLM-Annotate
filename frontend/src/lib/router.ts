/**
 * Hand-rolled hash routing. No router library is used.
 *
 * Supported URLs (Design Description v1.2, 6.3, adapted to hash routing):
 *   #/                                           datasets list
 *   #/signin, #/forgot-password, #/invite/:token  account pages
 *   #/datasets/:id                               dataset page (videos, searches)
 *   #/datasets/:id/searches/new                  new search
 *   #/datasets/:id/searches/:searchId            search status
 *   #/datasets/:id/searches/:searchId/review     review screen
 *   #/export?dataset=:id                         export view
 *   #/users                                      user management
 *
 * Old links (`#/projects/:id`, `#/projects/:id/review`) still resolve to the
 * dataset page, because a dataset is backed by a project in the current API.
 */
import { useEffect, useState } from "react";

export interface ParsedPath {
  pathname: string;
  query: URLSearchParams;
}

export type Route =
  | { name: "datasets" }
  | { name: "signin" }
  | { name: "forgot" }
  | { name: "invite"; token: string }
  | { name: "dataset"; datasetId: number }
  | { name: "newSearch"; datasetId: number }
  | { name: "search"; datasetId: number; searchId: number }
  | { name: "review"; datasetId: number; searchId: number }
  | { name: "export"; datasetId: number | null }
  | { name: "users" }
  | { name: "notFound"; pathname: string };

/** Splits `#/datasets/1/searches/2?x=y` into a normalised path and a query. */
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
  const notFound: Route = { name: "notFound", pathname };

  if (segments.length === 0) {
    return { name: "datasets" };
  }
  const [head, ...rest] = segments;

  if (rest.length === 0) {
    if (head === "signin") return { name: "signin" };
    if (head === "forgot-password") return { name: "forgot" };
    if (head === "users") return { name: "users" };
    if (head === "datasets") return { name: "datasets" };
    if (head === "export") return { name: "export", datasetId: toPositiveInt(query.get("dataset")) };
    return notFound;
  }

  if (head === "invite" && rest.length === 1) {
    const token = rest[0];
    return /^[A-Za-z0-9_-]{20,200}$/.test(token) ? { name: "invite", token } : notFound;
  }

  if (head === "datasets" || head === "projects") {
    const datasetId = toPositiveInt(rest[0]);
    if (datasetId === null) {
      return notFound;
    }
    if (rest.length === 1) {
      return { name: "dataset", datasetId };
    }
    if (head === "projects") {
      // Legacy review links: the dataset page lists every search.
      return rest.length === 2 && rest[1] === "review" ? { name: "dataset", datasetId } : notFound;
    }
    if (rest[1] !== "searches") {
      return notFound;
    }
    if (rest.length === 3 && rest[2] === "new") {
      return { name: "newSearch", datasetId };
    }
    const searchId = toPositiveInt(rest[2]);
    if (searchId === null) {
      return notFound;
    }
    if (rest.length === 3) {
      return { name: "search", datasetId, searchId };
    }
    if (rest.length === 4 && rest[3] === "review") {
      return { name: "review", datasetId, searchId };
    }
  }
  return notFound;
}

function currentRoute(): Route {
  if (typeof window === "undefined") {
    return { name: "datasets" };
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

/** Navigates to an in-app path such as `/datasets/1/searches/2/review`. */
export function navigate(path: string): void {
  const target = path.startsWith("/") ? path : `/${path}`;
  window.location.hash = target;
}

/** `href` for use in plain anchors. */
export function href(path: string): string {
  return `#${path.startsWith("/") ? path : `/${path}`}`;
}
