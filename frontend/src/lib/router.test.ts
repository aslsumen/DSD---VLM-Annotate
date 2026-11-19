import { describe, expect, it } from "vitest";

import { href, parseHash, parseRoute } from "./router";

describe("parseHash", () => {
  it("treats an empty hash as the root", () => {
    expect(parseHash("")).toEqual({ pathname: "/", query: new URLSearchParams() });
    expect(parseHash("#")).toEqual({ pathname: "/", query: new URLSearchParams() });
    expect(parseHash("#/")).toEqual({ pathname: "/", query: new URLSearchParams() });
  });

  it("normalises paths and strips trailing slashes", () => {
    expect(parseHash("#/datasets/12/").pathname).toBe("/datasets/12");
    expect(parseHash("#datasets/12").pathname).toBe("/datasets/12");
  });

  it("parses the query string", () => {
    const parsed = parseHash("#/export?dataset=42");
    expect(parsed.pathname).toBe("/export");
    expect(parsed.query.get("dataset")).toBe("42");
  });
});

describe("parseRoute", () => {
  it("routes to the datasets list", () => {
    expect(parseRoute("#/")).toEqual({ name: "datasets" });
    expect(parseRoute("")).toEqual({ name: "datasets" });
    expect(parseRoute("#/datasets")).toEqual({ name: "datasets" });
  });

  it("routes the account pages", () => {
    expect(parseRoute("#/signin")).toEqual({ name: "signin" });
    expect(parseRoute("#/forgot-password")).toEqual({ name: "forgot" });
    const token = "abcdefghijklmnopqrstuvwxyz_0123456789-AB";
    expect(parseRoute(`#/invite/${token}`)).toEqual({ name: "invite", token });
    expect(parseRoute("#/invite/short").name).toBe("notFound");
  });

  it("routes datasets, searches and review", () => {
    expect(parseRoute("#/datasets/7")).toEqual({ name: "dataset", datasetId: 7 });
    expect(parseRoute("#/datasets/7/searches/new")).toEqual({ name: "newSearch", datasetId: 7 });
    expect(parseRoute("#/datasets/7/searches/3")).toEqual({
      name: "search",
      datasetId: 7,
      searchId: 3,
    });
    expect(parseRoute("#/datasets/7/searches/3/review")).toEqual({
      name: "review",
      datasetId: 7,
      searchId: 3,
    });
  });

  it("keeps old project links working", () => {
    expect(parseRoute("#/projects/7")).toEqual({ name: "dataset", datasetId: 7 });
    expect(parseRoute("#/projects/7/review?job=3")).toEqual({ name: "dataset", datasetId: 7 });
  });

  it("routes export and users", () => {
    expect(parseRoute("#/export")).toEqual({ name: "export", datasetId: null });
    expect(parseRoute("#/export?dataset=4")).toEqual({ name: "export", datasetId: 4 });
    expect(parseRoute("#/export?dataset=x")).toEqual({ name: "export", datasetId: null });
    expect(parseRoute("#/users")).toEqual({ name: "users" });
  });

  it("rejects unknown or malformed paths", () => {
    expect(parseRoute("#/datasets/abc")).toEqual({ name: "notFound", pathname: "/datasets/abc" });
    expect(parseRoute("#/datasets/0")).toEqual({ name: "notFound", pathname: "/datasets/0" });
    expect(parseRoute("#/elsewhere")).toEqual({ name: "notFound", pathname: "/elsewhere" });
    expect(parseRoute("#/datasets/1/unknown").name).toBe("notFound");
    expect(parseRoute("#/datasets/1/searches/x").name).toBe("notFound");
    expect(parseRoute("#/projects/1/unknown").name).toBe("notFound");
  });
});

describe("href", () => {
  it("builds hash links", () => {
    expect(href("/datasets/1")).toBe("#/datasets/1");
    expect(href("datasets/1")).toBe("#/datasets/1");
  });
});
