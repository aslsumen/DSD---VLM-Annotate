import { describe, expect, it } from "vitest";
import { reviewInterval } from "./reviewBounds";

describe("the interval confirmed by the reviewer", () => {
  it.each([
    ["0", "2.264", 0, 2.264],
    [" ,125 ", "1.800", 0.125, 1.8],
    ["0.001", "0.002", 0.001, 0.002],
    ["1.0000", "3", 1, 3],
  ] as const)("reads both visible fields %s and %s exactly", (a, b, start, end) => {
    expect(reviewInterval(a, b, 3)).toEqual({ start, end });
  });
  it.each([
    ["", "2"], ["1", " "], ["-", "2"], ["0", "Infinity"], ["-0.1", "2"],
    ["1e0", "2"], ["0", "0x2"], ["0.0001", "2"], ["0", "2.1234"],
    ["2", "1"], ["1", "1"], ["0", "3.001"], ["0", "1,2.3"],
  ])("blocks %j to %j without changing the text", (start, end) => {
    expect(reviewInterval(start, end, 3)).toHaveProperty("error");
  });
});
