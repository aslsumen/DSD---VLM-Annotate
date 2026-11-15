import { describe, expect, it } from "vitest";

import { href, parseHash, parseRoute } from "./router";

describe("parseHash", () => {
  it("treats an empty hash as the projects route", () => {
    expect(parseHash("")).toEqual({ pathname: "/", query: new URLSearchParams() });
    expect(parseHash("#")).toEqual({ pathname: "/", query: new URLSearchParams() });
    expect(parseHash("#/")).toEqual({ pathname: "/", query: new URLSearchParams() });
  });

  it("normalises paths and strips trailing slashes", () => {
    expect(parseHash("#/projects/12/").pathname).toBe("/projects/12");
    expect(parseHash("#projects/12").pathname).toBe("/projects/12");
  });

  it("parses the query string", () => {
    const parsed = parseHash("#/projects/3/review?job=42");
    expect(parsed.pathname).toBe("/projects/3/review");
    expect(parsed.query.get("job")).toBe("42");
  });
});

describe("parseRoute", () => {
  it("routes to the projects list", () => {
    expect(parseRoute("#/")).toEqual({ name: "projects" });
    expect(parseRoute("")).toEqual({ name: "projects" });
  });

  it("routes to a project workspace", () => {
    expect(parseRoute("#/projects/7")).toEqual({ name: "project", projectId: 7 });
  });

  it("routes to review with and without a job id", () => {
    expect(parseRoute("#/projects/7/review?job=3")).toEqual({
      name: "review",
      projectId: 7,
      jobId: 3,
    });
    expect(parseRoute("#/projects/7/review")).toEqual({
      name: "review",
      projectId: 7,
      jobId: null,
    });
    expect(parseRoute("#/projects/7/review?job=abc").name).toBe("review");
  });

  it("rejects unknown or malformed paths", () => {
    expect(parseRoute("#/projects/abc")).toEqual({ name: "notFound", pathname: "/projects/abc" });
    expect(parseRoute("#/projects/0")).toEqual({ name: "notFound", pathname: "/projects/0" });
    expect(parseRoute("#/elsewhere")).toEqual({ name: "notFound", pathname: "/elsewhere" });
    expect(parseRoute("#/projects/1/unknown")).toEqual({
      name: "notFound",
      pathname: "/projects/1/unknown",
    });
  });
});

describe("href", () => {
  it("builds hash links", () => {
    expect(href("/projects/1")).toBe("#/projects/1");
    expect(href("projects/1")).toBe("#/projects/1");
  });
});
